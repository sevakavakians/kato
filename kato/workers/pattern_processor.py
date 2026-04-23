import asyncio
import heapq
import itertools
import logging
from collections import Counter, deque
from itertools import chain
from math import log, log2
from operator import itemgetter
from os import environ
from typing import Any, Optional

import numpy as np
from kato.informatics.knowledge_base import SuperKnowledgeBase
from kato.informatics.metrics import (
    accumulate_metadata,
    average_emotives,
    confluence,
)
from kato.informatics.predictive_information import calculate_ensemble_predictive_information
from kato.representations.pattern import Pattern
from kato.searches.pattern_search import PatternSearcher
from kato.storage.aggregation_pipelines import OptimizedQueryManager
from kato.storage.metrics_cache import CachedMetricsCalculator, get_metrics_cache_manager
from kato.storage.connection_manager import OptimizedConnectionManager
from kato.config.session_config import SessionConfiguration

# Standard logger configuration
logger = logging.getLogger('kato.pattern_processor')
logger.setLevel(getattr(logging, environ.get('LOG_LEVEL', 'INFO')))

class PatternProcessor:
    """
    Responsible for creating new, recognizing known, discovering unknown, and predicting patterns.

    Patterns can be temporal (sequences) or non-temporal (profiles). This processor manages
    short-term memory (STM), pattern learning, and prediction generation.

    Attributes:
        name: Name of the processor instance.
        kb_id: Knowledge base identifier for database connections.
        max_pattern_length: Maximum allowed pattern length.
        persistence: Number of events to retain in memory.
        recall_threshold: Minimum similarity threshold for pattern matching.
        STM: Short-term memory deque containing observed events.
        predictions_kb: Redis-backed interface for storing predictions.
    """
    def __init__(self, settings=None, **kwargs: Any) -> None:
        logger.debug("Starting PatternProcessor...")
        logger.debug(f"PatternProcessor kwargs: {kwargs}")
        self.settings = settings  # Store settings for passing to SuperKnowledgeBase
        self.name = f"{kwargs['name']}-PatternProcessor"
        self.kb_id = kwargs["kb_id"] # Use this to connect to the KB.
        self.max_pattern_length = kwargs["max_pattern_length"]
        self.persistence = kwargs["persistence"]
        self.max_predictions = int(kwargs["max_predictions"])
        self.recall_threshold = float(kwargs["recall_threshold"])
        self.stm_mode = kwargs.get("stm_mode", "CLEAR")  # Default to CLEAR for backward compatibility
        self.calculate_predictive_information = kwargs.get("calculate_predictive_information", False)  # Default to False

        # Get use_token_matching from kwargs (fallback to environment variable for backward compatibility)
        self.use_token_matching = kwargs.get("use_token_matching",
                                            environ.get('KATO_USE_TOKEN_MATCHING', 'true').lower() == 'true')

        # Get rank_sort_algo from kwargs (default to 'potential')
        self.rank_sort_algo = kwargs.get("rank_sort_algo", "potential")

        # AUTO-TOGGLE SORT based on use_token_matching
        # Token-level matching requires sort=True for consistent symbol matching
        # Character-level matching requires sort=False to preserve string order
        if "use_token_matching" in kwargs:
            if "sort" not in kwargs:
                # Auto-set sort based on matching mode
                self.sort = self.use_token_matching
                logger.info(f"Auto-toggled sort={self.sort} based on use_token_matching={self.use_token_matching}")
            else:
                # User explicitly set sort - warn if mismatch
                user_sort = kwargs.get("sort")
                if user_sort != self.use_token_matching:
                    logger.warning(
                        f"CONFIGURATION MISMATCH: sort={user_sort} with use_token_matching={self.use_token_matching}. "
                        f"Token-level matching requires sort=True, character-level requires sort=False. "
                        f"Using user-specified sort={user_sort}, but this may cause incorrect matching behavior."
                    )
                self.sort = user_sort
        else:
            # use_token_matching not in kwargs - use existing sort behavior
            self.sort = kwargs.get("sort", environ.get('SORT', 'true').lower() == 'true')

        self.superkb = SuperKnowledgeBase(self.kb_id, self.persistence, settings=self.settings)

        # Check architecture mode from environment
        arch_mode = environ.get('KATO_ARCHITECTURE_MODE', 'hybrid').lower()

        # Initialize PatternSearcher with appropriate configuration
        searcher_kwargs = {
            'kb_id': self.kb_id,
            'max_predictions': self.max_predictions,
            'recall_threshold': self.recall_threshold,
            'use_token_matching': self.use_token_matching
        }

        # Initialize hybrid architecture (ClickHouse + Redis)
        logger.info("=" * 60)
        logger.info("HYBRID ARCHITECTURE MODE ENABLED")
        logger.info("=" * 60)
        logger.info("Initializing ClickHouse/Redis connections...")

        # Get connection manager
        conn_manager = OptimizedConnectionManager()

        # Test ClickHouse connection (required)
        clickhouse_client = conn_manager.clickhouse
        if clickhouse_client is None:
            raise RuntimeError(
                "ClickHouse client is None! "
                "Possible causes:\n"
                "  1. ClickHouse service not running (check: docker ps | grep clickhouse)\n"
                "  2. Connection failed (check: curl http://localhost:8123/ping)\n"
                "  3. Environment variables incorrect (CLICKHOUSE_HOST, CLICKHOUSE_PORT)\n"
                "  4. clickhouse-connect library not installed\n"
                "Run: docker compose logs clickhouse"
            )

        # Verify ClickHouse query
        try:
            clickhouse_client.query("SELECT 1")
            logger.info("✓ ClickHouse connection verified")
        except Exception as ch_error:
            raise RuntimeError(
                f"ClickHouse connection test failed: {ch_error}\n"
                f"  Host: {environ.get('CLICKHOUSE_HOST', 'localhost')}\n"
                f"  Port: {environ.get('CLICKHOUSE_PORT', '9000')}\n"
                f"Run: docker exec kato-clickhouse clickhouse-client --query 'SELECT 1'"
            ) from ch_error

        # Test Redis connection (required)
        redis_client = conn_manager.redis
        if redis_client is None:
            raise RuntimeError(
                "Redis client is None! "
                "Possible causes:\n"
                "  1. Redis service not running (check: docker ps | grep redis)\n"
                "  2. Connection failed (check: docker exec kato-redis redis-cli ping)\n"
                "  3. Environment variables incorrect (REDIS_URL)\n"
                "  4. redis library not installed\n"
                "Run: docker compose logs redis"
            )

        # Verify Redis ping
        try:
            redis_client.ping()
            logger.info("✓ Redis connection verified")
        except Exception as redis_error:
            raise RuntimeError(
                f"Redis connection test failed: {redis_error}\n"
                f"  URL: {environ.get('REDIS_URL', 'redis://localhost:6379')}\n"
                f"Run: docker exec kato-redis redis-cli ping"
            ) from redis_error

        # Check pattern data status
        try:
            pattern_count = clickhouse_client.query("SELECT COUNT(*) FROM kato.patterns_data").result_rows[0][0]
            logger.info(f"ClickHouse patterns_data table: {pattern_count:,} rows")

            if pattern_count == 0:
                logger.info(
                    "ℹ️  patterns_data table is empty (fresh deployment).\n"
                    "  Patterns will accumulate as you train the system."
                )
        except Exception as check_error:
            logger.error(f"Failed to check patterns_data: {check_error}")

        # Create default session config for filter pipeline
        session_config = SessionConfiguration(
            filter_pipeline=[],
            minhash_threshold=0.7,
            length_min_ratio=0.5,
            length_max_ratio=2.0,
            jaccard_threshold=0.3,
            jaccard_min_overlap=2,
            recall_threshold=self.recall_threshold,
            use_token_matching=self.use_token_matching,
            enable_filter_metrics=True
        )

        # Add hybrid params to searcher
        searcher_kwargs.update({
            'session_config': session_config,
            'clickhouse_client': clickhouse_client,
            'redis_client': redis_client
        })

        logger.info("=" * 60)
        logger.info("✓ HYBRID ARCHITECTURE CONFIGURED SUCCESSFULLY")
        logger.info("=" * 60)

        self.patterns_searcher = PatternSearcher(**searcher_kwargs)

        # Initialize optimized query manager for aggregation pipelines
        self.query_manager = OptimizedQueryManager(self.superkb)

        # Initialize metrics cache
        self.metrics_cache_manager = None
        self.cached_calculator = None

        self.initiateDefaults()
        self.predict = True
        self.predictions_kb = self.superkb.predictions_kb
        self.predictions = []  # Cache for most recent predictions
        self.mood = {}
        self.target_class = None
        self.target_class_candidates = []
        self.future_potentials = []  # Store aggregated future potentials for API
        # Prediction-level caches (invalidated on learn())
        self._global_metadata_cache = None  # Caches get_global_metadata() result
        logger.info(f"PatternProcessor {self.name} started!")
        return

    def setSTM(self, x: list[list[str]]) -> None:
        """Set the short-term memory to a specific state.

        Args:
            x: List of events, where each event is a list of symbol strings.
        """
        self.STM = deque(x)
        return

    def clear_stm(self) -> None:
        """Clear the short-term memory and reset related state.

        Empties the STM deque, disables prediction triggering, and clears emotives and metadata.
        """
        self.STM: deque[list[str]] = deque()
        self.trigger_predictions: bool = False
        self.emotives: list[dict[str, float]] = []
        self.metadata: list[dict[str, Any]] = []
        return

    def clear_all_memory(self) -> None:
        """Clear all memory including STM and long-term patterns.

        Resets the entire processor state including short-term memory,
        learned patterns cache, and observation counters.
        """
        self.clear_stm()
        self.last_learned_pattern_name: Optional[str] = None
        self.patterns_searcher.clearPatternsFromRAM()

        # Delete all patterns from ClickHouse for this processor
        # This ensures test isolation and prevents pattern contamination
        self.superkb.patterns_kb.delete_many({})
        logger.info(f"Deleted all patterns for processor {self.kb_id}")

        # Also clear symbols and predictions
        self.superkb.symbols_kb.delete_many({})
        self.superkb.predictions_kb.delete_many({})

        self.superkb.patterns_observation_count = 0
        self.superkb.symbols_observation_count = 0
        # Invalidate caches since all data was cleared
        self.query_manager.invalidate_caches()
        self._global_metadata_cache = None
        self.initiateDefaults()
        return

    def initiateDefaults(self) -> None:
        """Initialize default values for processor state.

        Sets up empty STM, emotives, metadata, mood.
        Called during initialization and memory clearing.

        Note: Patterns are loaded lazily on-demand when predictions are needed,
        not during initialization. This avoids unnecessary database queries.
        """
        self.STM: deque[list[str]] = deque()
        self.emotives: list[dict[str, float]] = []
        self.metadata: list[dict[str, Any]] = []
        self.mood: dict[str, float] = {}
        self.last_learned_pattern_name: Optional[str] = None
        # Patterns are loaded lazily in PatternSearcher.causalBelief() when needed
        self.trigger_predictions: bool = False
        return

    async def initialize_metrics_cache(self) -> None:
        """Initialize the metrics cache manager and cached calculator."""
        try:
            self.metrics_cache_manager = await get_metrics_cache_manager()
            if self.metrics_cache_manager:
                self.cached_calculator = CachedMetricsCalculator(self.metrics_cache_manager)
                logger.info(f"Metrics cache initialized for processor {self.kb_id}")
            else:
                logger.warning(f"Metrics cache not available for processor {self.kb_id}")
        except Exception as e:
            logger.warning(f"Failed to initialize metrics cache for processor {self.kb_id}: {e}")
            self.metrics_cache_manager = None
            self.cached_calculator = None

    def learn(self) -> Optional[str]:
        """
        Convert current short-term memory into a persistent pattern.

        Creates a hash-named pattern from the data in STM, stores it in ClickHouse/Redis,
        and distributes it to search workers for future pattern matching.

        Returns:
            Pattern name (PTRN|<hash>) if learned successfully, None otherwise.
        """
        pattern = Pattern(self.STM)  # Create pattern from short-term memory data
        self.STM.clear()  # Reset short-term memory after learning

        if len(pattern) > 1:  # Only learn multi-event patterns
            # Store pattern with emotives as rolling window list and accumulated metadata
            x = self.patterns_kb.learnPattern(
                pattern,
                emotives=self.emotives,  # Keep as list - do NOT average before storage
                metadata=accumulate_metadata(self.metadata) if self.metadata else {}
            )

            if x:
                # Add newly learned pattern to the searcher
                # Index parameter kept for backward compatibility but ignored by optimized version
                self.patterns_searcher.assignNewlyLearnedToWorkers(
                    0,  # Index parameter ignored in optimized implementation
                    pattern.name,
                    pattern.flat_data
                )

                # Invalidate metrics cache since patterns have changed
                if self.metrics_cache_manager:
                    asyncio.create_task(
                        self.metrics_cache_manager.invalidate_pattern_metrics(pattern.name)
                    )

            # Invalidate symbol cache since symbol stats changed
            self.query_manager.invalidate_caches()
            self._global_metadata_cache = None  # Invalidate global metadata cache

            self.last_learned_pattern_name = pattern.name
            del(pattern)
            self.emotives = []
            self.metadata = []
            return self.last_learned_pattern_name
        self.emotives = []
        self.metadata = []
        return None

    async def finalize_training(self) -> dict[str, Any]:
        """
        Post-training step: compute and store pattern-intrinsic metrics.

        Computes Shannon entropy and TF (term frequency) vectors for every
        pattern in this kb_id, then stores them in Redis. These metrics only
        depend on the pattern's own symbol distribution and are immutable once
        the pattern is learned, but they require corpus-level statistics
        (total_symbols, total_unique_patterns) that are only stable after
        training completes.

        Should be called once after a training session is finished.

        Returns:
            Summary dict with patterns_processed, time_ms, and status.
        """
        import time
        start = time.perf_counter()

        # Flush pending ClickHouse writes so all patterns are visible.
        # flush_if_pending is a no-op now (client-side buffer is always empty
        # with batch_size=1), but flush_async_insert_queue drains the server-
        # side async_insert buffer — necessary since wait_for_async_insert=0
        # means learn() returns before rows are durably in the target table.
        self.superkb.clickhouse_writer.flush_if_pending()
        self.superkb.clickhouse_writer.flush_async_insert_queue()

        # Query all patterns for this kb_id from ClickHouse
        from kato.storage.connection_manager import get_clickhouse_client
        clickhouse_client = get_clickhouse_client()
        if not clickhouse_client:
            raise RuntimeError("ClickHouse not available for finalize_training")

        result = clickhouse_client.query(
            f"SELECT name, pattern_data FROM kato.patterns_data "
            f"WHERE kb_id = '{self.superkb.id}'"
        )

        if not result.result_rows:
            return {
                'status': 'completed',
                'patterns_processed': 0,
                'time_ms': round((time.perf_counter() - start) * 1000, 2)
            }

        # Load corpus-level statistics needed for normalized entropy metrics
        all_symbols = self.superkb.redis_writer.get_all_symbols_batch()
        total_symbols = len(all_symbols)
        global_metadata = self.superkb.redis_writer.get_global_metadata()
        total_unique_patterns = global_metadata.get('total_unique_patterns', 1)

        # Build symbol_probability_cache: P(symbol) = pattern_member_frequency / total_unique_patterns
        symbol_probability_cache = {}
        for symbol_name, symbol_data in all_symbols.items():
            if total_unique_patterns > 0:
                symbol_probability_cache[symbol_name] = float(
                    symbol_data.get('pattern_member_frequency', 0) / total_unique_patterns
                )
            else:
                symbol_probability_cache[symbol_name] = 0.0

        # Compute all pattern-intrinsic metrics
        metrics_batch = []
        for row in result.result_rows:
            pattern_name, pattern_data = row

            # Flatten event-structured pattern_data to symbol list
            pattern_symbols = [s for event in pattern_data for s in event]
            pattern_length = len(pattern_symbols)

            if pattern_length == 0:
                continue

            symbol_counts = Counter(pattern_symbols)

            # Shannon entropy: H = -Σ (p_i * log2(p_i))
            entropy_val = 0.0
            for count in symbol_counts.values():
                if count > 0:
                    p = count / pattern_length
                    entropy_val -= p * log2(p)

            # Normalized entropy: Σ expectation(count/length, total_symbols)
            # Uses log base = total_symbols (matching metrics.py:expectation)
            normalized_entropy_val = 0.0
            if total_symbols > 1:
                for count in symbol_counts.values():
                    if count > 0:
                        p = count / pattern_length
                        normalized_entropy_val -= p * log(p, total_symbols)

            # Global normalized entropy: Σ expectation(symbol_prob, total_symbols)
            # Uses global symbol probabilities from the corpus
            global_normalized_entropy_val = 0.0
            if total_symbols > 1:
                for symbol in set(pattern_symbols):
                    prob = symbol_probability_cache.get(symbol, 0)
                    if prob > 0:
                        global_normalized_entropy_val -= prob * log(prob, total_symbols)

            # TF vector: {symbol: count / pattern_length}
            tf_vector = {
                symbol: count / pattern_length
                for symbol, count in symbol_counts.items()
            }

            metrics_batch.append({
                'pattern_name': pattern_name,
                'entropy': entropy_val,
                'normalized_entropy': normalized_entropy_val,
                'global_normalized_entropy': global_normalized_entropy_val,
                'tf_vector': tf_vector
            })

        # Batch-write to Redis
        written = self.superkb.redis_writer.write_precomputed_metrics_batch(metrics_batch)

        elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
        logger.info(
            f"finalize_training: computed metrics for {written} patterns "
            f"in {elapsed_ms}ms (kb_id={self.kb_id})"
        )

        return {
            'status': 'completed',
            'patterns_processed': written,
            'time_ms': elapsed_ms
        }

    def delete_pattern(self, name: str) -> str:
        if not self.patterns_searcher.delete_pattern(name):
            raise Exception(f'Unable to find and delete pattern {name} in RAM')
        # Delete from ClickHouse
        try:
            self.superkb.clickhouse_writer.client.command(
                f"ALTER TABLE kato.patterns_data DELETE WHERE kb_id = '{self.kb_id}' AND name = '{name}'"
            )
        except Exception as e:
            logger.warning(f"Failed to delete pattern {name} from ClickHouse: {e}")
        # Delete metadata from Redis
        try:
            for key_type in ['frequency', 'emotives', 'metadata']:
                self.superkb.redis_writer.client.delete(f"{self.kb_id}:{key_type}:{name}")
        except Exception as e:
            logger.warning(f"Failed to delete pattern {name} metadata from Redis: {e}")
        # Invalidate symbol cache since pattern data changed
        self.query_manager.invalidate_caches()
        return 'deleted'

    def update_pattern(self, name: str, frequency: int, emotives: dict[str, list[float]]) -> Optional[dict[str, Any]]:
        """Update a pattern's frequency and emotional values.

        Args:
            name: Pattern name to update.
            frequency: New frequency value.
            emotives: Dictionary of emotional values.

        Returns:
            Updated pattern document or None if not found.

        Raises:
            Exception: If emotive array exceeds persistence limit.
        """
        for emotive, values_list in emotives.items():
            if len(values_list) > self.persistence:
                raise Exception(f'{emotive} array length ({len(values_list)}) exceeds system persistence ({self.persistence})')
        # Update metadata in Redis
        self.superkb.redis_writer.write_metadata(name, frequency=frequency, emotives=emotives)
        return {'name': name, 'frequency': frequency, 'emotives': emotives}

    async def processEvents(self, current_unique_id: str) -> list[dict[str, Any]]:
        """
        Generate predictions by matching short-term memory against learned patterns.

        Flattens the STM (list of events) into a single state vector,
        then searches for similar patterns in the pattern database.
        Predictions are cached in Redis for retrieval.

        Args:
            current_unique_id: Unique identifier for this observation.

        Returns:
            List of prediction dictionaries with pattern matches and metrics.

        Note:
            KATO requires at least 1 string in STM to generate predictions.
        """
        # Flatten short-term memory: [["a","b"],["c"]] -> ["a","b","c"]
        state = list(chain(*self.STM))

        # Generate predictions if we have at least 1 string in state
        # Single-symbol predictions use optimized fast path
        if len(state) >= 1 and self.predict and self.trigger_predictions:
            predictions = await self.predictPattern(state, stm_events=self.STM)

            # Cache predictions in memory for quick access
            self.predictions = predictions

            # Store predictions for async retrieval
            if predictions:
                self.predictions_kb.insert_one({
                    'unique_id': current_unique_id,
                    'predictions': predictions
                })
            return predictions

        # Return empty predictions if state is too short
        return []

    def setCurrentEvent(self, symbols: list[str]) -> None:
        """
        Add a new event (list of symbols) to short-term memory.

        Short-term memory is a deque of events, where each event is a list of symbols
        observed at the same time. E.g., STM = [["cat","dog"], ["bird"], ["cat"]]

        Args:
            symbols: List of symbol strings to add as a new event.
        """
        if symbols:
            self.STM.append(symbols)
        return

    def maintain_rolling_window(self, max_length: int) -> None:
        """
        Maintain STM as a rolling window of fixed size.

        If STM exceeds max_length, removes the oldest event(s) to maintain the window size.
        Used in ROLLING mode to keep STM at a fixed size after auto-learning.

        Args:
            max_length: Maximum number of events to keep in STM
        """
        while len(self.STM) > max_length:
            removed_event = self.STM.popleft()
            logger.debug(f"Rolling window: removed oldest event {removed_event}")
        logger.debug(f"Rolling window: STM maintained at length {len(self.STM)}")
        return

    def symbolFrequency(self, symbol: str) -> int:
        """Get the frequency count for a symbol.

        Args:
            symbol: Symbol name to look up.

        Returns:
            Frequency count of the symbol.
        """
        # Use batch query for better performance
        # No fallback - fail fast if Redis is unavailable
        symbol_stats = self.query_manager.get_symbol_frequencies_batch([symbol])
        return symbol_stats.get(symbol, 0)

    def symbolProbability(self, symbol: str, total_unique_patterns: int) -> float:
        """Calculate the probability of a symbol appearing in patterns.

        Args:
            symbol: Symbol name to calculate probability for.
            total_unique_patterns: Total number of unique patterns (NOT frequency-weighted).

        Returns:
            Probability value between 0.0 and 1.0.
        """
        # FIX: Use pattern_member_frequency / total_unique_patterns for compatible units
        # This gives us the probability that a randomly selected pattern contains this symbol

        # Use batch query for better performance
        # No fallback - fail fast if Redis is unavailable
        symbol_stats = self.query_manager.get_symbol_frequencies_batch([symbol])
        symbol_data = symbol_stats.get(symbol, {})
        pattern_member_frequency = symbol_data.get('pattern_member_frequency', 0)
        return float(pattern_member_frequency / total_unique_patterns) if total_unique_patterns > 0 else 0.0

    def patternProbability(self, freq: int, total_pattern_frequencies: int) -> float:
        """Calculate the probability of a pattern based on its frequency.

        Args:
            freq: Frequency of the specific pattern.
            total_pattern_frequencies: Total frequency across all patterns.

        Returns:
            Probability value between 0.0 and 1.0.
        """
        return float(freq/total_pattern_frequencies) if total_pattern_frequencies > 0 else 0.0

    def _compute_affinity_weights(self, state: list[str], candidate_patterns: list[dict] = None) -> Optional[dict[str, float]]:
        """
        Compute affinity-weighted token weights for pattern matching.

        Uses frequency-normalized absolute affinity: w(t) = |aff(t, e)| / freq(t) + epsilon

        Args:
            state: Flattened STM state tokens
            candidate_patterns: Optional list of candidate pattern dicts (for single-symbol path).
                If None, weights are computed only for state tokens (pattern tokens
                will get floor weight if not in the weight map).

        Returns:
            Dict mapping symbol -> weight, or None if affinity weighting is not active.
        """
        # Check if affinity_emotive is configured (session_config lives on the PatternSearcher)
        affinity_emotive = None
        if hasattr(self, 'patterns_searcher') and self.patterns_searcher:
            sc = getattr(self.patterns_searcher, 'session_config', None)
            if sc:
                affinity_emotive = getattr(sc, 'affinity_emotive', None)

        if not affinity_emotive:
            return None

        EPSILON = 0.01

        # Collect all unique symbols that need weights
        all_symbols = set(state)
        if candidate_patterns:
            for p in candidate_patterns:
                for event in p.get('pattern_data', []):
                    all_symbols.update(event)

        all_symbols = list(all_symbols)
        if not all_symbols:
            return None

        # Batch fetch affinities and frequencies from Redis
        affinities = self.superkb.redis_writer.get_symbol_affinity_batch(all_symbols)
        frequencies = self.superkb.redis_writer.get_symbol_frequencies_batch(all_symbols)

        # Compute weights: w(t) = |aff(t, e)| / freq(t) + epsilon
        weights = {}
        for symbol in all_symbols:
            aff_dict = affinities.get(symbol, {})
            aff_value = abs(aff_dict.get(affinity_emotive, 0.0))
            freq = frequencies.get(symbol, 0)
            if freq > 0 and aff_value > 0:
                weights[symbol] = aff_value / freq + EPSILON
            else:
                weights[symbol] = EPSILON

        return weights

    async def _predict_single_symbol_fast(self, symbol: str, stm_events: Optional[list[list[str]]] = None) -> list[dict[str, Any]]:
        """
        Fast path for single-symbol predictions using Redis symbol-to-pattern index.

        Bypasses the expensive filter pipeline and directly loads patterns containing
        the symbol, then filters to patterns starting with the symbol.

        Args:
            symbol: Single symbol to match
            stm_events: Short-term memory events (for temporal segmentation)

        Returns:
            List of prediction dictionaries sorted by potential

        Performance:
            10-1000x faster than full filter pipeline for single-symbol queries.
            O(1) Redis lookup + O(k) ClickHouse batch load where k = matching patterns
        """
        logger.info(f"*** {self.name} [ PatternProcessor _predict_single_symbol_fast called with symbol='{symbol}' ]")

        # Flush any pending ClickHouse writes so recently learned patterns are visible
        self.superkb.clickhouse_writer.flush_if_pending()

        try:
            # Step 1: Query ClickHouse directly for patterns starting with this symbol
            # Uses the first_token column (populated during _prepare_row) instead of
            # building a large IN-clause from Redis, which overflows max_query_size at scale.
            from kato.storage.connection_manager import get_clickhouse_client
            clickhouse_client = get_clickhouse_client()

            if not clickhouse_client:
                logger.warning("ClickHouse not available, falling back to regular prediction path")
                return await self.predictPattern([symbol], stm_events=stm_events)

            query = f"""
                SELECT name, pattern_data, length
                FROM kato.patterns_data
                WHERE kb_id = '{self.superkb.id}' AND first_token = '{symbol}'
            """

            result = clickhouse_client.query(query)

            if not result.result_rows:
                logger.debug(f"No patterns found starting with symbol '{symbol}'")
                return []

            logger.debug(f"Found {len(result.result_rows)} patterns starting with symbol '{symbol}'")

            # Step 2: Build candidate list (all rows already start with this symbol)
            candidate_patterns = []
            for row in result.result_rows:
                pattern_name, pattern_data, length = row
                if pattern_data and pattern_data[0] and pattern_data[0][0] == symbol:
                    candidate_patterns.append({
                        'name': pattern_name,
                        'pattern_data': pattern_data,
                        'length': length
                    })

            if not candidate_patterns:
                logger.debug(f"No patterns START with symbol '{symbol}' (found patterns containing it)")
                return []

            logger.debug(f"Found {len(candidate_patterns)} patterns STARTING with symbol '{symbol}'")

            # Step 4: Calculate similarity and metrics for each candidate
            # Use the existing InformationExtractor for consistency
            from kato.searches.pattern_search import InformationExtractor
            extractor = InformationExtractor(
                use_fast_matcher=True,
                use_token_matching=self.use_token_matching
            )

            state = [symbol]  # Single-symbol state
            predictions = []

            # For single-symbol predictions, use a very low threshold (0.0)
            # since we're already filtering to patterns that START with this symbol.
            single_symbol_threshold = 0.0

            # Pre-load all pattern metadata in a single batch call
            candidate_names = [p['name'] for p in candidate_patterns]
            metadata_batch = self.superkb.redis_writer.get_metadata_batch(candidate_names)

            # Compute affinity weights if affinity_emotive is configured
            affinity_weights = self._compute_affinity_weights(state, candidate_patterns)

            def _process_single_symbol_batch(batch, _state, _extractor, _metadata_batch, _threshold, _weights=None):
                """Process a batch of candidates for single-symbol prediction (thread-safe)."""
                batch_results = []
                for pattern_dict in batch:
                    pattern_data_flat = list(chain(*pattern_dict['pattern_data']))

                    prediction_info = _extractor.extract_prediction_info(
                        pattern_data_flat,
                        _state,
                        cutoff=_threshold,
                        fuzzy_token_threshold=0.0,
                        weights=_weights
                    )

                    if not prediction_info:
                        continue

                    (pattern, matching_intersection, past, present, missing, extras,
                     similarity, number_of_blocks, anomalies, weighted_similarity) = prediction_info

                    metadata = _metadata_batch.get(pattern_dict['name'], {'name': pattern_dict['name'], 'frequency': 1})
                    frequency = metadata.get('frequency', 1)
                    # Floor frequency at 1: pattern exists in ClickHouse, so frequency=0
                    # indicates Redis data loss, not an unlearned pattern
                    if frequency == 0:
                        logger.warning(
                            f"Pattern {pattern_dict['name']} found in ClickHouse but has "
                            f"frequency=0 in Redis — possible Redis data loss. Defaulting to 1."
                        )
                        frequency = 1
                    emotives = metadata.get('emotives', [])

                    total_pattern_symbols = len(pattern)
                    evidence = len(matching_intersection) / total_pattern_symbols if total_pattern_symbols > 0 else 0.0

                    if present:
                        present_flat = list(chain(*present)) if isinstance(present[0], list) else present
                    else:
                        present_flat = []

                    total_present_symbols = len(present_flat)
                    confidence = len(matching_intersection) / total_present_symbols if total_present_symbols > 0 else 0.0

                    total_matches = len(matching_intersection)
                    total_extras = len(extras)
                    snr = total_matches / (total_matches + total_extras) if (total_matches + total_extras) > 0 else 0.0

                    fragmentation = number_of_blocks - 1

                    # Compute weighted metrics if weights available
                    weighted_evidence = None
                    weighted_confidence = None
                    weighted_snr = None
                    if _weights:
                        w_matched = sum(_weights.get(t, 0.0) for t in matching_intersection)
                        w_pattern = sum(_weights.get(t, 0.0) for t in pattern)
                        w_present = sum(_weights.get(t, 0.0) for t in present_flat)
                        w_extras = sum(_weights.get(t, 0.0) for t in extras)

                        weighted_evidence = (w_matched / w_pattern) if w_pattern > 0 else 0.0
                        weighted_confidence = (w_matched / w_present) if w_present > 0 else 0.0
                        weighted_snr = (w_matched / (w_matched + w_extras)) if (w_matched + w_extras) > 0 else 0.0

                    try:
                        if isinstance(emotives, list) and emotives:
                            emotives = average_emotives(emotives)
                        elif not emotives:
                            emotives = {}
                    except ZeroDivisionError:
                        emotives = {}

                    batch_results.append({
                        'name': pattern_dict['name'],
                        'pattern_data': pattern_dict['pattern_data'],
                        'length': pattern_dict['length'],
                        'frequency': frequency,
                        'emotives': emotives,
                        'matches': matching_intersection,
                        'missing': missing,
                        'present': present,
                        'past': past,
                        'future': pattern[len(past) + len(present_flat):] if len(past) + len(present_flat) < len(pattern) else [],
                        'extras': extras,
                        'similarity': similarity,
                        'evidence': evidence,
                        'confidence': confidence,
                        'snr': snr,
                        'fragmentation': fragmentation,
                        'anomalies': anomalies,
                        'weighted_similarity': weighted_similarity,
                        'weighted_evidence': weighted_evidence,
                        'weighted_confidence': weighted_confidence,
                        'weighted_snr': weighted_snr
                    })
                return batch_results

            # Parallel processing for large candidate sets, sequential for small
            import multiprocessing
            import concurrent.futures
            SINGLE_SYMBOL_PARALLEL_THRESHOLD = 100

            if len(candidate_patterns) > SINGLE_SYMBOL_PARALLEL_THRESHOLD:
                max_workers = min(multiprocessing.cpu_count(), 8)
                batch_sz = max(1, len(candidate_patterns) // max_workers)
                batches = [candidate_patterns[i:i + batch_sz] for i in range(0, len(candidate_patterns), batch_sz)]

                with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                    futures = [
                        executor.submit(_process_single_symbol_batch, batch, state, extractor, metadata_batch, single_symbol_threshold, affinity_weights)
                        for batch in batches
                    ]
                    for future in concurrent.futures.as_completed(futures):
                        try:
                            predictions.extend(future.result())
                        except Exception as e:
                            logger.error(f"Error processing single-symbol batch: {e}")
            else:
                predictions.extend(
                    _process_single_symbol_batch(candidate_patterns, state, extractor, metadata_batch, single_symbol_threshold, affinity_weights)
                )

            if not predictions:
                logger.debug(f"No predictions passed similarity threshold for symbol '{symbol}'")
                return []

            # Step 5: Calculate metrics using existing infrastructure
            # This is the same as the regular predictPattern path
            # (We'll call the same metric calculation code)

            # For now, return predictions without full metric calculations
            # The regular predictPattern will calculate all metrics
            # But we need to at least calculate potential for sorting

            for prediction in predictions:
                frag = prediction['fragmentation']
                frag_contribution = 0.0 if frag == -1 else (1 / (frag + 1))

                # Use weighted metrics for potential when available
                ev = prediction.get('weighted_evidence') if prediction.get('weighted_evidence') is not None else prediction['evidence']
                conf = prediction.get('weighted_confidence') if prediction.get('weighted_confidence') is not None else prediction['confidence']
                s = prediction.get('weighted_snr') if prediction.get('weighted_snr') is not None else prediction['snr']

                prediction['potential'] = (
                    (ev + conf) * s
                    + frag_contribution
                )

            # Sort by potential
            predictions.sort(key=lambda x: x['potential'], reverse=True)

            # Limit to max_predictions
            predictions = predictions[:self.max_predictions]

            logger.debug(f"Returning {len(predictions)} predictions for single-symbol '{symbol}'")
            return predictions

        except Exception as e:
            logger.error(f"Error in _predict_single_symbol_fast for symbol '{symbol}': {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            # Fall back to regular prediction path
            logger.warning("Falling back to regular prediction path")
            return await self.predictPattern([symbol], stm_events=stm_events)

    async def predictPattern(self, state: list[str], stm_events: Optional[list[list[str]]] = None, max_workers: Optional[int] = None, batch_size: int = 100) -> list[dict[str, Any]]:
        """Predict patterns matching the given state (async with caching support).

        Provides 3-10x performance improvement through:
        - Parallel pattern matching using ThreadPoolExecutor
        - Async database queries for metadata and symbols
        - Concurrent metric calculations using asyncio.gather
        - Batched processing to optimize memory usage

        Single-symbol optimization:
        - Uses fast path with Redis symbol-to-pattern index (10-1000x faster)
        - Bypasses expensive filter pipeline
        - Direct ClickHouse batch loading

        Args:
            state: Flattened list of symbols representing current STM state.
            max_workers: Maximum number of worker threads (defaults to CPU count)
            batch_size: Number of patterns per batch for parallel processing

        Returns:
            List of prediction dictionaries sorted by potential, containing
            pattern information and calculated metrics.

        Raises:
            Exception: If async pattern search fails.
            ValueError: If predictions are missing required fields.
        """
        logger.info(f"*** {self.name} [ PatternProcessor predictPattern (async) called with state={state} ]")

        # Flush any pending ClickHouse writes so recently learned patterns are visible
        self.superkb.clickhouse_writer.flush_if_pending()

        # FAST PATH: Single-symbol predictions using Redis index
        if len(state) == 1:
            logger.info(f"Using single-symbol fast path for state={state}")
            return await self._predict_single_symbol_fast(state[0], stm_events=stm_events)

        try:
            # Compute and set affinity weights on pattern searcher before matching
            self.patterns_searcher.affinity_weights = self._compute_affinity_weights(state)

            # Use async parallel pattern matching
            causal_patterns = await self.patterns_searcher.causalBeliefAsync(
                state, self.target_class_candidates, stm_events, max_workers, batch_size)
        except Exception as e:
            raise Exception(f"\nException in PatternProcessor.predictPattern: Error in causalBeliefAsync! {self.kb_id}: {e}")

        # Early return if no patterns found
        if not causal_patterns:
            self.future_potentials = []  # Clear stale future_potentials
            logger.debug(f" {self.name} [ PatternProcessor predictPattern (async) ] No causal patterns found, returning empty list")
            return []

        # Validate all predictions have required fields (same validation as sync version)
        for idx, prediction in enumerate(causal_patterns):
            required_fields = ['frequency', 'matches', 'missing', 'evidence',
                              'confidence', 'snr', 'fragmentation', 'emotives', 'present']
            missing_fields = []
            for field in required_fields:
                if field not in prediction:
                    missing_fields.append(field)
            if missing_fields:
                pred_name = prediction.get('name', f'prediction_{idx}')
                raise ValueError(f"Prediction '{pred_name}' missing required fields: {missing_fields}")

        # Compute weighted metrics for predictions if affinity weighting is active
        weights = self.patterns_searcher.affinity_weights
        if weights:
            for p in causal_patterns:
                matches = p.get('matches', [])
                present_events = p.get('present', [])
                extras = p.get('extras', [])
                pattern_data = p.get('pattern_data', [])

                from itertools import chain as _chain
                present_flat = list(_chain(*present_events)) if present_events and isinstance(present_events[0], list) else (present_events or [])
                pattern_flat = list(_chain(*pattern_data)) if pattern_data and isinstance(pattern_data[0], list) else (pattern_data or [])

                # Handle event-structured extras
                if extras and isinstance(extras[0], list):
                    extras_flat = list(_chain(*extras))
                else:
                    extras_flat = extras or []

                w_matched = sum(weights.get(t, 0.0) for t in matches)
                w_pattern = sum(weights.get(t, 0.0) for t in pattern_flat)
                w_present = sum(weights.get(t, 0.0) for t in present_flat)
                w_extras = sum(weights.get(t, 0.0) for t in extras_flat)

                p['weighted_evidence'] = (w_matched / w_pattern) if w_pattern > 0 else 0.0
                p['weighted_confidence'] = (w_matched / w_present) if w_present > 0 else 0.0
                p['weighted_snr'] = (w_matched / (w_matched + w_extras)) if (w_matched + w_extras) > 0 else 0.0

        # Top-K pruning: reduce candidates before expensive metrics loop
        # Uses a cheap pre-potential from already-available fields (same formula as
        # final potential minus itfdf_similarity which hasn't been computed yet).
        # itfdf_similarity is bounded [0,1], so a 3x safety margin prevents losing
        # high-quality predictions that might reorder after full metrics.
        PRUNING_FACTOR = 3
        max_for_metrics = self.max_predictions * PRUNING_FACTOR
        if len(causal_patterns) > max_for_metrics:
            original_count = len(causal_patterns)
            for p in causal_patterns:
                frag = p['fragmentation']
                p['_pre_potential'] = (
                    (p['evidence'] + p['confidence']) * p['snr']
                    + (0.0 if frag == -1 else 1.0 / (frag + 1))
                )
            causal_patterns = heapq.nlargest(max_for_metrics, causal_patterns, key=itemgetter('_pre_potential'))
            logger.debug(f"Top-K pruning: kept {len(causal_patterns)} of {original_count} candidates for metrics loop")

        try:
            # Pre-calculate symbol probability cache using optimized aggregation pipeline
            symbol_probability_cache = {}
            total_ensemble_pattern_frequencies = 0

            # Load global metadata from Redis (cached across prediction calls, invalidated on learn)
            if self._global_metadata_cache is None:
                self._global_metadata_cache = self.superkb.redis_writer.get_global_metadata()
            global_metadata = self._global_metadata_cache
            total_symbols_in_patterns_frequencies = global_metadata.get('total_symbols_in_patterns_frequencies', 0)
            total_pattern_frequencies = global_metadata.get('total_pattern_frequencies', 0)
            total_unique_patterns = global_metadata.get('total_unique_patterns', 1)  # Use 1 to avoid div by zero

            # Load all symbols using optimized aggregation pipeline (internally cached by QueryManager)
            symbol_cache = self.query_manager.get_all_symbols_optimized(
                self.superkb.symbols_kb
            )
            total_symbols = len(symbol_cache)
            logger.debug(f"Loaded {total_symbols} symbols using optimized aggregation pipeline (async)")

            # Calculate totals and caches
            for prediction in causal_patterns:
                total_ensemble_pattern_frequencies += prediction['frequency']
                # Flatten missing if it's event-structured (list of lists)
                missing_symbols_calc = prediction['missing']
                if missing_symbols_calc and isinstance(missing_symbols_calc[0], list):
                    missing_symbols_calc = [s for event in missing_symbols_calc for s in event]
                for symbol in itertools.chain(prediction['matches'], missing_symbols_calc):
                    if symbol not in symbol_probability_cache:
                        if symbol not in symbol_cache:
                            symbol_probability_cache[symbol] = 0
                            continue
                        symbol_data = symbol_cache[symbol]
                        # FIX: Use total_unique_patterns for pattern-based probability (compatible units)
                        if total_unique_patterns > 0:
                            # Probability that a random pattern contains this symbol
                            symbol_probability = float(symbol_data['pattern_member_frequency'] / total_unique_patterns)
                        else:
                            symbol_probability = 0.0
                        symbol_probability_cache[symbol] = symbol_probability

            symbol_frequency_in_state = Counter(state)

            if total_ensemble_pattern_frequencies == 0:
                logger.warning(f" {self.name} [ PatternProcessor predictPattern (async) ] total_ensemble_pattern_frequencies is 0")

            # Batch-load pre-computed pattern-intrinsic metrics from Redis
            # (entropy, normalized_entropy, global_normalized_entropy, tf_vector)
            prediction_names = [p.get('name', '') for p in causal_patterns]
            precomputed_metrics = self.superkb.redis_writer.get_precomputed_metrics_batch(prediction_names)
            precomputed_hit = len(precomputed_metrics)
            precomputed_miss = len(prediction_names) - precomputed_hit
            if precomputed_hit > 0:
                logger.debug(f"Pre-computed metrics: {precomputed_hit} hits, {precomputed_miss} misses")

            # Vectorized cosine distance: batch compute all distances before the loop
            N = len(causal_patterns)
            present_lists = []
            all_present_symbols = set()
            for prediction in causal_patterns:
                _present = list(chain(*prediction.present))
                present_lists.append(_present)
                all_present_symbols.update(_present)

            global_symbols = sorted(all_present_symbols | set(state))
            symbol_to_idx = {s: i for i, s in enumerate(global_symbols)}
            D = len(global_symbols)

            # Pre-compute state vector once (weighted by symbol_probability_cache)
            state_vec = np.zeros(D)
            for symbol, count in symbol_frequency_in_state.items():
                if symbol in symbol_to_idx:
                    state_vec[symbol_to_idx[symbol]] = symbol_probability_cache.get(symbol, 0) * count
            state_norm = np.linalg.norm(state_vec)

            # Build pattern frequency matrix (N x D)
            pattern_matrix = np.zeros((N, D))
            for i, _present in enumerate(present_lists):
                for symbol, count in Counter(_present).items():
                    if symbol in symbol_to_idx:
                        pattern_matrix[i, symbol_to_idx[symbol]] = symbol_probability_cache.get(symbol, 0) * count

            # Batch cosine distance computation
            if state_norm > 0:
                dots = pattern_matrix @ state_vec
                pattern_norms = np.linalg.norm(pattern_matrix, axis=1)
                denom = pattern_norms * state_norm
                cosine_sims = np.where(denom > 0, dots / denom, 0.0)
                distances = 1.0 - cosine_sims
            else:
                distances = np.ones(N)

            # Process predictions with metrics calculations
            for i, prediction in enumerate(causal_patterns):
                _present = present_lists[i]
                distance = float(distances[i])
                _p_e_h = float(self.patternProbability(prediction['frequency'], total_pattern_frequencies))

                if total_ensemble_pattern_frequencies > 0:
                    itfdf_similarity = 1 - (distance * prediction['frequency'] / total_ensemble_pattern_frequencies)
                else:
                    itfdf_similarity = 0.0

                # Calculate confluence with conditional probability caching if available
                # Let exceptions propagate - client should receive HTTP 500 on calculation failure
                if len(_present) > 0:
                    if self.cached_calculator:
                        try:
                            conditional_prob = await self.cached_calculator.conditional_probability_cached(
                                _present, symbol_probability_cache
                            )
                            confluence_val = _p_e_h * (1 - conditional_prob)
                        except Exception as e:
                            logger.debug(f"Cached conditional probability failed: {e}, falling back to direct calculation")
                            confluence_val = _p_e_h * (1 - confluence(_present, symbol_probability_cache))
                    else:
                        confluence_val = _p_e_h * (1 - confluence(_present, symbol_probability_cache))
                else:
                    confluence_val = 0.0

                # Average emotives (convert from list of dicts to single dict)
                try:
                    if isinstance(prediction['emotives'], list):
                        prediction['emotives'] = average_emotives(prediction['emotives'])
                except ZeroDivisionError as e:
                    logger.error(f"ZeroDivisionError in average_emotives: emotives={prediction['emotives']}, error={e}")
                    raise

                # Pattern-intrinsic entropy metrics: use pre-computed if available
                pred_name = prediction.get('name', '')
                precomp = precomputed_metrics.get(pred_name)

                if precomp:
                    entropy_val = precomp['entropy']
                    normalized_entropy_val = precomp['normalized_entropy']
                    global_normalized_entropy_val = precomp['global_normalized_entropy']
                else:
                    # Fallback: compute at runtime (pattern predates finalize-training)
                    pattern_symbols = [s for event in prediction['present'] for s in event]
                    pattern_length = len(pattern_symbols)
                    if pattern_symbols:
                        symbol_counts = Counter(pattern_symbols)
                        # Shannon entropy (log base 2)
                        entropy_val = 0.0
                        for count in symbol_counts.values():
                            if count > 0:
                                p = count / pattern_length
                                entropy_val -= p * log2(p)
                        # Normalized entropy (log base total_symbols)
                        normalized_entropy_val = 0.0
                        if total_symbols > 1:
                            for count in symbol_counts.values():
                                if count > 0:
                                    p = count / pattern_length
                                    normalized_entropy_val -= p * log(p, total_symbols)
                        # Global normalized entropy (using symbol probabilities)
                        global_normalized_entropy_val = 0.0
                        if total_symbols > 1:
                            for symbol in set(pattern_symbols):
                                prob = symbol_probability_cache.get(symbol, 0)
                                if prob > 0:
                                    global_normalized_entropy_val -= prob * log(prob, total_symbols)
                    else:
                        entropy_val = 0.0
                        normalized_entropy_val = 0.0
                        global_normalized_entropy_val = 0.0

                # TF-IDF: use pre-computed TF vector if available, else compute at runtime
                if precomp and total_unique_patterns > 0:
                    tf_vector = precomp['tf_vector']
                    tfidf_scores = []
                    for symbol, tf in tf_vector.items():
                        if symbol in symbol_probability_cache:
                            patterns_with_symbol = int(symbol_probability_cache[symbol] * total_unique_patterns)
                            if patterns_with_symbol == 0:
                                patterns_with_symbol = 1
                        else:
                            patterns_with_symbol = 1
                        idf = log2(total_unique_patterns / patterns_with_symbol) + 1
                        tfidf_scores.append(tf * idf)
                    tfidf_score = sum(tfidf_scores) / len(tfidf_scores) if tfidf_scores else 0.0
                else:
                    # Fallback: compute TF and IDF at runtime
                    if not precomp:
                        pattern_symbols = [s for event in prediction['present'] for s in event]
                    else:
                        pattern_symbols = []  # precomp exists but total_unique_patterns == 0
                    unique_symbols = set(pattern_symbols)
                    pattern_length = len(pattern_symbols)

                    if pattern_length > 0 and total_unique_patterns > 0:
                        tfidf_scores = []
                        for symbol in unique_symbols:
                            tf = pattern_symbols.count(symbol) / pattern_length
                            if symbol in symbol_probability_cache:
                                patterns_with_symbol = int(symbol_probability_cache[symbol] * total_unique_patterns)
                                if patterns_with_symbol == 0:
                                    patterns_with_symbol = 1
                            else:
                                patterns_with_symbol = 1
                            idf = log2(total_unique_patterns / patterns_with_symbol) + 1
                            tfidf_scores.append(tf * idf)
                        tfidf_score = sum(tfidf_scores) / len(tfidf_scores) if tfidf_scores else 0.0
                    else:
                        tfidf_score = 0.0

                # Update prediction with calculated values
                prediction.update({
                    'entropy': entropy_val,
                    'normalized_entropy': normalized_entropy_val,
                    'global_normalized_entropy': global_normalized_entropy_val,
                    'itfdf_similarity': itfdf_similarity,
                    'confluence': confluence_val,
                    'tfidf_score': tfidf_score
                })

                # Remove pattern_data to save bandwidth
                prediction.pop('pattern_data', None)

            # Calculate ensemble-based predictive information for metrics
            # Let exceptions propagate - client should receive HTTP 500 on calculation failure
            causal_patterns, future_potentials = calculate_ensemble_predictive_information(causal_patterns)
            # Store future_potentials for the API response
            self.future_potentials = future_potentials

            # Vectorized Bayesian posterior probabilities
            # P(pattern|obs) = P(obs|pattern) × P(pattern) / P(obs)
            freqs = np.array([p.get('frequency', 1) for p in causal_patterns], dtype=float)
            sims = np.array([p['similarity'] for p in causal_patterns], dtype=float)
            sum_freqs = freqs.sum()

            if sum_freqs > 0:
                priors = freqs / sum_freqs
                evidence_sum = np.dot(sims, priors)
                if evidence_sum > 0:
                    posteriors = (sims * priors) / evidence_sum
                else:
                    posteriors = np.zeros(len(freqs))
                for i, p in enumerate(causal_patterns):
                    p['bayesian_posterior'] = float(posteriors[i])
                    p['bayesian_prior'] = float(priors[i])
                    p['bayesian_likelihood'] = float(sims[i])
            else:
                for p in causal_patterns:
                    p['bayesian_posterior'] = 0.0
                    p['bayesian_prior'] = 0.0
                    p['bayesian_likelihood'] = p['similarity']

            logger.debug(f"Calculated Bayesian posteriors for {len(causal_patterns)} predictions")

            # Vectorized potential calculation
            # potential = (evidence + confidence) * snr + itfdf_similarity + (1/(fragmentation + 1))
            # Use weighted metrics when available
            use_weighted = weights and any(p.get('weighted_evidence') is not None for p in causal_patterns)
            evidence_arr = np.array([p.get('weighted_evidence', p['evidence']) if use_weighted else p['evidence'] for p in causal_patterns])
            confidence_arr = np.array([p.get('weighted_confidence', p['confidence']) if use_weighted else p['confidence'] for p in causal_patterns])
            snr_arr = np.array([p.get('weighted_snr', p['snr']) if use_weighted else p['snr'] for p in causal_patterns])
            itfdf_arr = np.array([p.get('itfdf_similarity', 0.0) for p in causal_patterns])
            frag_arr = np.array([p['fragmentation'] for p in causal_patterns])
            frag_contrib = np.where(frag_arr == -1, 0.0, 1.0 / (frag_arr + 1))
            potentials = (evidence_arr + confidence_arr) * snr_arr + itfdf_arr + frag_contrib
            for i, p in enumerate(causal_patterns):
                p['potential'] = float(potentials[i])

            try:
                # Sort predictions using configurable ranking algorithm (default: 'potential')
                active_causal_patterns = sorted(
                    list(heapq.nlargest(self.max_predictions, causal_patterns, key=itemgetter(self.rank_sort_algo))),
                    reverse=True,
                    key=itemgetter(self.rank_sort_algo)
                )
            except KeyError as e:
                raise ValueError(f"Invalid rank_sort_algo '{self.rank_sort_algo}': metric not found in predictions. Available metrics: {list(causal_patterns[0].keys()) if causal_patterns else 'none'}")
            except Exception as e:
                raise Exception(f"\nException in PatternProcessor.predictPattern (async): Error in sorting predictions! {self.kb_id}: {e}")

            logger.debug(f" [ PatternProcessor predictPattern (async) ] {len(active_causal_patterns)} active_causal_patterns")
            return active_causal_patterns

        except Exception as e:
            raise Exception(f"\nException in PatternProcessor.predictPattern (async): Error in metrics calculation! {self.kb_id}: {e}")

    async def get_predictions_async(self, stm: list[list[str]], config=None) -> list[dict[str, Any]]:
        """
        Generate predictions with session-specific configuration (async version).

        This is the config-as-parameter version that doesn't mutate processor state.

        Args:
            stm: Short-term memory (list of events)
            config: Optional SessionConfiguration with prediction parameters

        Returns:
            List of prediction dictionaries
        """
        # Flatten STM to state
        state = list(chain(*stm))

        # Generate predictions if we have at least 1 string in state
        # Single-symbol predictions use optimized fast path
        if len(state) < 1:
            logger.debug("No symbols in state for predictions")
            return []

        # Extract config values or use instance defaults
        recall_threshold = config.recall_threshold if config and config.recall_threshold is not None else self.recall_threshold
        max_predictions = config.max_predictions if config and config.max_predictions is not None else self.max_predictions
        use_token_matching = config.use_token_matching if config and config.use_token_matching is not None else self.use_token_matching

        # Temporarily create a PatternSearcher with config values
        # This avoids mutating the instance's patterns_searcher
        # Use same architecture mode as main searcher
        temp_searcher_kwargs = {
            'kb_id': self.kb_id,
            'max_predictions': max_predictions,
            'recall_threshold': recall_threshold,
            'use_token_matching': use_token_matching
        }

        # Check if main searcher is using hybrid architecture
        if hasattr(self.patterns_searcher, 'use_hybrid_architecture') and self.patterns_searcher.use_hybrid_architecture:
            # Pass hybrid parameters from main searcher
            temp_searcher_kwargs.update({
                'session_config': config if config else self.patterns_searcher.session_config,
                'clickhouse_client': self.patterns_searcher.clickhouse_client,
                'redis_client': self.patterns_searcher.redis_client
            })

        temp_searcher = PatternSearcher(**temp_searcher_kwargs)

        # Save original searcher
        original_searcher = self.patterns_searcher
        original_max_predictions = self.max_predictions

        try:
            # Temporarily swap searcher and max_predictions
            self.patterns_searcher = temp_searcher
            self.max_predictions = max_predictions

            # Call predictPattern with the provided STM
            predictions = await self.predictPattern(state, stm_events=stm)

            return predictions or []
        finally:
            # Restore original searcher and max_predictions
            self.patterns_searcher = original_searcher
            self.max_predictions = original_max_predictions

    def get_predictions(self, stm: list[list[str]], config=None) -> list[dict[str, Any]]:
        """
        Generate predictions with session-specific configuration (sync wrapper).

        This is a synchronous wrapper around get_predictions_async.

        Args:
            stm: Short-term memory (list of events)
            config: Optional SessionConfiguration with prediction parameters

        Returns:
            List of prediction dictionaries
        """
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If we're in an async context, create a task
                return asyncio.create_task(self.get_predictions_async(stm, config))
            else:
                return loop.run_until_complete(self.get_predictions_async(stm, config))
        except RuntimeError:
            # No event loop, create one
            return asyncio.run(self.get_predictions_async(stm, config))
