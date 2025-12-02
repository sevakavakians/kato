import asyncio
import heapq
import itertools
import logging
from collections import Counter, deque
from itertools import chain
from math import log2
from operator import itemgetter
from os import environ
from typing import Any, Optional

import numpy as np
import pymongo
from pymongo import ReturnDocument

from kato.informatics.knowledge_base import SuperKnowledgeBase
from kato.informatics.metrics import (
    accumulate_metadata,
    average_emotives,
    confluence,
    global_normalized_entropy,
    normalized_entropy,
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
        predictions_kb: MongoDB collection for storing predictions.
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
        arch_mode = environ.get('KATO_ARCHITECTURE_MODE', 'mongodb').lower()

        # Initialize PatternSearcher with appropriate configuration
        searcher_kwargs = {
            'kb_id': self.kb_id,
            'max_predictions': self.max_predictions,
            'recall_threshold': self.recall_threshold,
            'use_token_matching': self.use_token_matching
        }

        # Configure hybrid architecture if enabled
        if arch_mode == 'hybrid':
            # Check if strict mode is enabled (fails instead of falling back)
            strict_mode = environ.get('KATO_STRICT_MODE', 'false').lower() == 'true'

            try:
                logger.info("=" * 60)
                logger.info("HYBRID ARCHITECTURE MODE ENABLED")
                logger.info("=" * 60)
                logger.info("Initializing ClickHouse/Redis connections...")

                # Get connection manager
                conn_manager = OptimizedConnectionManager()

                # Test ClickHouse connection
                clickhouse_client = conn_manager.clickhouse
                if clickhouse_client is None:
                    error_msg = (
                        "ClickHouse client is None! "
                        "Possible causes:\n"
                        "  1. ClickHouse service not running (check: docker ps | grep clickhouse)\n"
                        "  2. Connection failed (check: curl http://localhost:8123/ping)\n"
                        "  3. Environment variables incorrect (CLICKHOUSE_HOST, CLICKHOUSE_PORT)\n"
                        "  4. clickhouse-connect library not installed\n"
                        "Run: docker-compose logs clickhouse"
                    )
                    logger.error(error_msg)
                    if strict_mode:
                        raise RuntimeError("ClickHouse required in strict mode but not available")
                    logger.warning("⚠️  Falling back to MongoDB mode")
                    arch_mode = 'mongodb'
                else:
                    # Test ClickHouse query
                    try:
                        result = clickhouse_client.query("SELECT 1")
                        logger.info("✓ ClickHouse connection verified")
                    except Exception as ch_error:
                        error_msg = (
                            f"ClickHouse connection test failed: {ch_error}\n"
                            f"  Host: {environ.get('CLICKHOUSE_HOST', 'localhost')}\n"
                            f"  Port: {environ.get('CLICKHOUSE_PORT', '9000')}\n"
                            f"Run: docker exec kato-clickhouse clickhouse-client --query 'SELECT 1'"
                        )
                        logger.error(error_msg)
                        if strict_mode:
                            raise RuntimeError(f"ClickHouse query failed: {ch_error}")
                        logger.warning("⚠️  Falling back to MongoDB mode")
                        arch_mode = 'mongodb'
                        clickhouse_client = None

                # Test Redis connection
                redis_client = conn_manager.redis
                if redis_client is None:
                    error_msg = (
                        "Redis client is None! "
                        "Possible causes:\n"
                        "  1. Redis service not running (check: docker ps | grep redis)\n"
                        "  2. Connection failed (check: docker exec kato-redis redis-cli ping)\n"
                        "  3. Environment variables incorrect (REDIS_URL)\n"
                        "  4. redis library not installed\n"
                        "Run: docker-compose logs redis"
                    )
                    logger.error(error_msg)
                    if strict_mode:
                        raise RuntimeError("Redis required in strict mode but not available")
                    logger.warning("⚠️  Falling back to MongoDB mode")
                    arch_mode = 'mongodb'
                else:
                    # Test Redis ping
                    try:
                        redis_client.ping()
                        logger.info("✓ Redis connection verified")
                    except Exception as redis_error:
                        error_msg = (
                            f"Redis connection test failed: {redis_error}\n"
                            f"  URL: {environ.get('REDIS_URL', 'redis://localhost:6379')}\n"
                            f"Run: docker exec kato-redis redis-cli ping"
                        )
                        logger.error(error_msg)
                        if strict_mode:
                            raise RuntimeError(f"Redis ping failed: {redis_error}")
                        logger.warning("⚠️  Falling back to MongoDB mode")
                        arch_mode = 'mongodb'
                        redis_client = None

                # Configure hybrid mode if both clients available
                if clickhouse_client and redis_client and arch_mode == 'hybrid':
                    # Check if data is migrated
                    try:
                        pattern_count = clickhouse_client.query("SELECT COUNT(*) FROM kato.patterns_data").result_rows[0][0]
                        logger.info(f"ClickHouse patterns_data table: {pattern_count:,} rows")

                        if pattern_count == 0:
                            logger.warning(
                                "⚠️  WARNING: patterns_data table is EMPTY!\n"
                                "  Hybrid mode will return no results until data is migrated.\n"
                                "  Run: python scripts/migrate_mongodb_to_clickhouse.py"
                            )
                            if strict_mode:
                                raise RuntimeError("ClickHouse table empty - run migration first")
                    except Exception as check_error:
                        logger.error(f"Failed to check patterns_data: {check_error}")
                        if strict_mode:
                            raise

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
                    logger.info("Filter pipeline: [] (no filtering - returns all patterns)")
                    logger.info("Performance: Unfiltered pattern retrieval")
                    logger.info("=" * 60)

            except Exception as e:
                import traceback
                error_details = traceback.format_exc()
                logger.error("=" * 60)
                logger.error("HYBRID ARCHITECTURE INITIALIZATION FAILED")
                logger.error("=" * 60)
                logger.error(f"Error: {e}")
                logger.error(f"Full traceback:\n{error_details}")
                logger.error("=" * 60)

                if strict_mode:
                    logger.error("STRICT MODE: Failing hard instead of falling back")
                    raise RuntimeError(f"Hybrid mode required but initialization failed: {e}")

                logger.warning("⚠️  FALLING BACK TO MONGODB MODE")
                logger.warning("Set KATO_STRICT_MODE=true to fail instead of fallback")
                arch_mode = 'mongodb'

        if arch_mode == 'mongodb':
            logger.info("MongoDB architecture mode active")

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

        # CRITICAL: Delete all patterns from MongoDB for this processor
        # This ensures test isolation and prevents pattern contamination
        deleted = self.superkb.patterns_kb.delete_many({})
        logger.info(f"Deleted {deleted.deleted_count} patterns from MongoDB for processor {self.kb_id}")

        # Also clear symbols and predictions
        self.superkb.symbols_kb.delete_many({})
        self.superkb.predictions_kb.delete_many({})

        self.superkb.patterns_observation_count = 0
        self.superkb.symbols_observation_count = 0
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

        Creates a hash-named pattern from the data in STM, stores it in MongoDB,
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
                    list(chain(*pattern.pattern_data))
                )

                # Invalidate metrics cache since patterns have changed
                if self.metrics_cache_manager:
                    asyncio.create_task(
                        self.metrics_cache_manager.invalidate_pattern_metrics(pattern.name)
                    )

            self.last_learned_pattern_name = pattern.name
            del(pattern)
            self.emotives = []
            self.metadata = []
            return self.last_learned_pattern_name
        self.emotives = []
        self.metadata = []
        return None

    def delete_pattern(self, name: str) -> str:
        if not self.patterns_searcher.delete_pattern(name):
            raise Exception(f'Unable to find and delete pattern {name} in RAM')
        result = self.patterns_kb.delete_one({"name": name})
        if result.deleted_count != 1:
            logger.warning(f'Expected to delete 1 record for pattern {name} but deleted {result.deleted_count}')
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
        return self.patterns_kb.find_one_and_update(
            {'name': name},
            {'$set': {'frequency': frequency, 'emotives': emotives}},
            {'_id': False},
            return_document=ReturnDocument.AFTER
        )

    async def processEvents(self, current_unique_id: str) -> list[dict[str, Any]]:
        """
        Generate predictions by matching short-term memory against learned patterns.

        Flattens the STM (list of events) into a single state vector,
        then searches for similar patterns in the pattern database.
        Predictions are cached in MongoDB for retrieval.

        Args:
            current_unique_id: Unique identifier for this observation.

        Returns:
            List of prediction dictionaries with pattern matches and metrics.

        Note:
            KATO requires at least 2 strings in STM to generate predictions.
        """
        # Flatten short-term memory: [["a","b"],["c"]] -> ["a","b","c"]
        state = list(chain(*self.STM))

        # Only generate predictions if we have at least 2 strings in state
        # KATO requires minimum 2 strings for pattern matching
        if len(state) >= 2 and self.predict and self.trigger_predictions:
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

    async def predictPattern(self, state: list[str], stm_events: Optional[list[list[str]]] = None, max_workers: Optional[int] = None, batch_size: int = 100) -> list[dict[str, Any]]:
        """Predict patterns matching the given state (async with caching support).

        Provides 3-10x performance improvement through:
        - Parallel pattern matching using ThreadPoolExecutor
        - Async database queries for metadata and symbols
        - Concurrent metric calculations using asyncio.gather
        - Batched processing to optimize memory usage

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

        # Fetch metadata concurrently
        total_symbols = self.superkb.symbols_kb.count_documents({})
        metadata_doc = self.superkb.metadata.find_one({"class": "totals"})
        if metadata_doc:
            total_symbols_in_patterns_frequencies = metadata_doc.get('total_symbols_in_patterns_frequencies', 0)
            total_pattern_frequencies = metadata_doc.get('total_pattern_frequencies', 0)
        else:
            total_symbols_in_patterns_frequencies = 0
            total_pattern_frequencies = 0

        try:
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

        try:
            # Pre-calculate symbol probability cache using optimized aggregation pipeline
            symbol_probability_cache = {}
            total_ensemble_pattern_frequencies = 0

            # Load global metadata from Redis (NEW)
            global_metadata = self.superkb.redis_writer.get_global_metadata()
            total_symbols_in_patterns_frequencies = global_metadata.get('total_symbols_in_patterns_frequencies', 0)
            total_pattern_frequencies = global_metadata.get('total_pattern_frequencies', 0)
            total_unique_patterns = global_metadata.get('total_unique_patterns', 1)  # Use 1 to avoid div by zero

            # Load all symbols using optimized aggregation pipeline
            # No fallback - fail fast if Redis is unavailable
            symbol_cache = self.query_manager.get_all_symbols_optimized(
                self.superkb.symbols_kb
            )
            logger.debug(f"Loaded {len(symbol_cache)} symbols using optimized aggregation pipeline (async)")

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

            # Process predictions with metrics calculations (same logic as sync version)
            for prediction in causal_patterns:
                _present = list(chain(*prediction.present))
                all_symbols = set(_present + state)
                symbol_frequency_in_pattern = Counter(_present)
                state_frequency_vector = [(symbol_probability_cache.get(symbol, 0) * symbol_frequency_in_state.get(symbol, 0)) for symbol in all_symbols]
                pattern_frequency_vector = [(symbol_probability_cache.get(symbol, 0) * symbol_frequency_in_pattern.get(symbol, 0)) for symbol in all_symbols]
                _p_e_h = float(self.patternProbability(prediction['frequency'], total_pattern_frequencies))

                # Calculate cosine distance using numpy (same as sync version)
                if all(v == 0 for v in state_frequency_vector) or all(v == 0 for v in pattern_frequency_vector):
                    distance = 1.0
                else:
                    try:
                        state_arr = np.array(state_frequency_vector)
                        pattern_arr = np.array(pattern_frequency_vector)
                        cosine_similarity = np.dot(state_arr, pattern_arr) / (np.linalg.norm(state_arr) * np.linalg.norm(pattern_arr))
                        distance = 1.0 - cosine_similarity
                    except Exception as e:
                        logger.warning(f"Error calculating cosine distance: {e}, using default")
                        distance = 1.0

                # Calculate all metrics with caching if available
                if self.cached_calculator and len(state) > 0:
                    try:
                        # Use cached metrics calculations
                        normalized_entropy_val = await self.cached_calculator.normalized_entropy_cached(
                            state, total_symbols
                        )
                        global_normalized_entropy_val = await self.cached_calculator.global_normalized_entropy_cached(
                            state, symbol_probability_cache, total_symbols
                        )
                    except Exception as e:
                        logger.warning(f"Cached metrics calculation failed: {e}, falling back to direct calculation")
                        normalized_entropy_val = normalized_entropy(state, total_symbols)
                        global_normalized_entropy_val = global_normalized_entropy(state, symbol_probability_cache, total_symbols)
                else:
                    # Fallback to direct calculation
                    normalized_entropy_val = normalized_entropy(state, total_symbols)
                    global_normalized_entropy_val = global_normalized_entropy(state, symbol_probability_cache, total_symbols)

                if total_ensemble_pattern_frequencies > 0:
                    itfdf_similarity = 1 - (distance * prediction['frequency'] / total_ensemble_pattern_frequencies)
                else:
                    itfdf_similarity = 0.0

                # Calculate confluence with conditional probability caching if available
                try:
                    if self.cached_calculator and len(_present) > 0:
                        try:
                            # Use cached conditional probability calculation
                            conditional_prob = await self.cached_calculator.conditional_probability_cached(
                                _present, symbol_probability_cache
                            )
                            confluence_val = _p_e_h * (1 - conditional_prob)
                        except Exception as e:
                            logger.debug(f"Cached conditional probability failed: {e}, falling back to direct calculation")
                            confluence_val = _p_e_h * (1 - confluence(_present, symbol_probability_cache))
                    else:
                        confluence_val = _p_e_h * (1 - confluence(_present, symbol_probability_cache))
                except Exception as e:
                    logger.debug(f"Error calculating confluence: {e}")
                    confluence_val = 0.0

                # Average emotives (convert from list of dicts to single dict)
                # Note: Emotives from Redis storage are already averaged (dict),
                # while emotives from in-memory patterns are lists that need averaging
                try:
                    if isinstance(prediction['emotives'], list):
                        prediction['emotives'] = average_emotives(prediction['emotives'])
                    # else: already a dict from storage, keep as-is
                except ZeroDivisionError as e:
                    logger.error(f"ZeroDivisionError in average_emotives: emotives={prediction['emotives']}, error={e}")
                    raise

                # Calculate Shannon entropy of the pattern's symbol distribution
                pattern_symbols = [s for event in prediction['present'] for s in event]
                if pattern_symbols:
                    symbol_counts = Counter(pattern_symbols)
                    total = len(pattern_symbols)
                    entropy_val = 0.0
                    for count in symbol_counts.values():
                        if count > 0:
                            p = count / total
                            entropy_val -= p * log2(p)
                else:
                    entropy_val = 0.0

                # Calculate TF-IDF score for this pattern
                tfidf_scores = []
                unique_symbols = set(pattern_symbols)
                pattern_length = len(pattern_symbols)

                if pattern_length > 0 and total_unique_patterns > 0:
                    for symbol in unique_symbols:
                        # Term Frequency: count of symbol in this pattern / pattern length
                        tf = pattern_symbols.count(symbol) / pattern_length

                        # Inverse Document Frequency: log(total patterns / patterns containing symbol) + 1
                        # Get symbol statistics from cache
                        if symbol in symbol_probability_cache:
                            # We already calculated probabilities, so back-calculate pattern_member_frequency
                            patterns_with_symbol = int(symbol_probability_cache[symbol] * total_unique_patterns)
                            if patterns_with_symbol == 0:
                                patterns_with_symbol = 1  # Avoid division by zero
                        else:
                            # Symbol not in cache, use default
                            patterns_with_symbol = 1

                        idf = log2(total_unique_patterns / patterns_with_symbol) + 1
                        tfidf_scores.append(tf * idf)

                    # Use mean aggregation for pattern-level TF-IDF
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
                    'tfidf_score': tfidf_score  # NEW metric
                })

                # Remove pattern_data to save bandwidth
                prediction.pop('pattern_data', None)

            # Calculate ensemble-based predictive information for metrics
            try:
                causal_patterns, future_potentials = calculate_ensemble_predictive_information(causal_patterns)
                # Store future_potentials for the API response
                self.future_potentials = future_potentials
            except Exception as e:
                logger.error(f"Error in ensemble predictive information calculation: {e}")
                # Set predictive_information to 0 if calculation fails
                for prediction in causal_patterns:
                    if 'predictive_information' not in prediction:
                        prediction['predictive_information'] = 0.0
                self.future_potentials = []

            # Calculate Bayesian posterior probabilities for ensemble
            # Uses Bayes' theorem: P(pattern|obs) = P(obs|pattern) × P(pattern) / P(obs)
            try:
                # Calculate sum of frequencies (for prior probabilities)
                sum_ensemble_frequencies = sum(p.get('frequency', 1) for p in causal_patterns)

                if sum_ensemble_frequencies > 0:
                    # Calculate evidence: P(obs) = Σ P(obs|pattern) × P(pattern)
                    # Where P(obs|pattern) = similarity and P(pattern) = frequency/total_freq
                    evidence_sum = sum(
                        p['similarity'] * (p.get('frequency', 1) / sum_ensemble_frequencies)
                        for p in causal_patterns
                    )

                    # Calculate posterior for each prediction
                    for prediction in causal_patterns:
                        frequency = prediction.get('frequency', 1)
                        similarity = prediction['similarity']

                        # Prior: P(pattern) = frequency / total_frequencies
                        prior = frequency / sum_ensemble_frequencies

                        # Likelihood: P(obs|pattern) = similarity score
                        likelihood = similarity

                        # Posterior: P(pattern|obs) using Bayes' theorem
                        if evidence_sum > 0:
                            posterior = (likelihood * prior) / evidence_sum
                        else:
                            posterior = 0.0

                        # Store Bayesian metrics
                        prediction['bayesian_posterior'] = posterior
                        prediction['bayesian_prior'] = prior
                        prediction['bayesian_likelihood'] = likelihood
                else:
                    # No valid frequencies - set all Bayesian metrics to 0
                    for prediction in causal_patterns:
                        prediction['bayesian_posterior'] = 0.0
                        prediction['bayesian_prior'] = 0.0
                        prediction['bayesian_likelihood'] = prediction['similarity']

                logger.debug(f"Calculated Bayesian posteriors for {len(causal_patterns)} predictions")

            except Exception as e:
                logger.error(f"Error in Bayesian posterior calculation: {e}")
                # Set Bayesian metrics to 0 if calculation fails
                for prediction in causal_patterns:
                    prediction['bayesian_posterior'] = 0.0
                    prediction['bayesian_prior'] = 0.0
                    prediction['bayesian_likelihood'] = prediction.get('similarity', 0.0)

            # Calculate potential using direct formula (overwrites any potential from calculate_ensemble_predictive_information)
            # potential = (evidence + confidence) * snr + itfdf_similarity + (1/(fragmentation + 1))
            # Handle fragmentation = -1 edge case (0 blocks, no matches) -> contribution = 0
            for prediction in causal_patterns:
                frag = prediction['fragmentation']
                frag_contribution = 0.0 if frag == -1 else (1 / (frag + 1))

                prediction['potential'] = (
                    (prediction['evidence'] + prediction['confidence']) * prediction['snr']
                    + prediction.get('itfdf_similarity', 0.0)
                    + frag_contribution
                )

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

        # Only generate predictions if we have at least 2 strings in state
        if len(state) < 2:
            logger.debug("Not enough symbols in state for predictions (need at least 2)")
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
