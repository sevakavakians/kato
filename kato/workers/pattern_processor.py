import asyncio
import itertools
import logging
from collections import Counter, deque
from itertools import chain
from math import log2
from os import environ
from typing import Any, Optional

import numpy as np

from kato.config.session_config import SessionConfiguration
from kato.exceptions import DataConsistencyError
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
from kato.representations.prediction import Prediction, rank_predictions
from kato.searches.pattern_search import PatternSearcher
from kato.storage.aggregation_pipelines import OptimizedQueryManager
from kato.storage.clickhouse_writer import ClickHouseWriter
from kato.storage.connection_manager import (
    OptimizedConnectionManager,
    get_connection_manager,
)
from kato.storage.identifiers import validate_kb_id, validate_pattern_name
from kato.storage.metrics_cache import CachedMetricsCalculator, get_metrics_cache_manager

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
            pattern_count = clickhouse_client.query(
                "SELECT COUNT(*) FROM kato.patterns_data WHERE kb_id = %(kb_id)s",
                parameters={'kb_id': self.kb_id},
            ).result_rows[0][0]
            logger.info(f"ClickHouse patterns_data for kb_id={self.kb_id}: {pattern_count:,} rows")

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

    def learn_from(
        self,
        stm: list[list[str]],
        emotives: list[dict[str, float]],
        metadata: list[dict[str, Any]],
    ) -> Optional[str]:
        """
        Convert the given short-term memory into a persistent pattern.

        Stateless with respect to STM: the caller owns `stm` and decides what
        becomes of it afterwards (cleared, rolled, or tail kept). Creates a
        hash-named pattern, stores it in ClickHouse/Redis, and distributes it to
        search workers for future pattern matching.

        Args:
            stm: Events to learn, oldest first.
            emotives: Rolling-window emotives to store with the pattern (kept as
                a list - never averaged before storage).
            metadata: Metadata dicts accumulated for the pattern.

        Returns:
            Pattern name (bare hash) if learned, None for patterns holding
            fewer than two symbols (which are not learned). The threshold is on
            symbols, not events: a single event of two or more symbols, e.g.
            [['hello', 'world']], is learned, and is a different pattern from
            the same symbols split across events, [['hello'], ['world']].
        """
        pattern = Pattern(list(stm))
        if len(pattern) <= 1:  # Pattern.__len__ counts symbols, not events
            return None

        x = self.patterns_kb.learnPattern(
            pattern,
            emotives=list(emotives),
            metadata=accumulate_metadata(metadata) if metadata else {}
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
        self.last_learned_pattern_name = pattern.name
        return pattern.name

    def learn(self) -> Optional[str]:
        """
        Learn from the processor's own STM, then clear it (legacy stateful form).

        Request paths use learn_from() with per-request state; this remains for
        callers that still drive the processor's instance STM.
        """
        name = self.learn_from(self.STM, self.emotives, self.metadata)
        self.STM.clear()  # Reset short-term memory after learning (even if nothing was learned)
        self.emotives = []
        self.metadata = []
        return name

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
            "SELECT name, pattern_data FROM kato.patterns_data "
            "WHERE kb_id = %(kb_id)s",
            parameters={'kb_id': self.superkb.id},
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

            # The prediction-time fallback calls the same two functions on the
            # same full pattern, so a pattern reports the same value whether or
            # not finalize_training has run.
            normalized_entropy_val = normalized_entropy(pattern_symbols, total_symbols)
            global_normalized_entropy_val = global_normalized_entropy(
                pattern_symbols, symbol_probability_cache, total_symbols
            )

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

        # Batch-write to the active metadata store(s) per the migration flags.
        written = self.superkb.metadata_router.update_precomputed_metrics_batch(metrics_batch)

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
        # The RAM copy is already gone at this point, so a failure below leaves
        # the pattern in persistent storage while the caller is told it was
        # deleted. Let these raise: a partial delete is a data-integrity
        # problem the caller must see, not a warning to scroll past.
        #
        # ALTER ... DELETE cannot bind parameters, so both identifiers are
        # allowlist-validated before being inlined.
        safe_kb_id = validate_kb_id(self.kb_id)
        safe_name = validate_pattern_name(name)
        self.superkb.clickhouse_writer.client.command(
            f"ALTER TABLE kato.patterns_data DELETE "
            f"WHERE kb_id = '{safe_kb_id}' AND name = '{safe_name}'"
        )
        # Frequency lives in Redis only — delete it directly.
        self.superkb.redis_writer.client.delete(f"{self.kb_id}:frequency:{name}")
        # Delete emotives/metadata/metric data from both stores via the router.
        self.superkb.metadata_router.delete_pattern_metadata(name)
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
        # Admin override: explicitly set frequency in Redis (the only path that bypasses
        # the SETNX/INCR atomic flow), then upsert emotives via the router.
        self.superkb.redis_writer.client.set(f"{self.kb_id}:frequency:{name}", frequency)
        self.superkb.metadata_router.upsert_pattern_metadata(
            pattern_name=name,
            emotives=emotives,
            metadata=None,
        )
        return {'name': name, 'frequency': frequency, 'emotives': emotives}

    async def predict_from(
        self,
        stm: list[list[str]],
        current_unique_id: str,
        trigger_predictions: bool = True,
    ) -> list[dict[str, Any]]:
        """
        Generate predictions by matching the given short-term memory against learned patterns.

        Flattens the STM (list of events) into a single state vector, then
        searches for similar patterns in the pattern database. Predictions are
        cached in Redis for retrieval by unique_id. Stateless with respect to STM.

        Args:
            stm: Events, oldest first.
            current_unique_id: Unique identifier for this observation.
            trigger_predictions: False disables prediction generation.

        Returns:
            List of prediction dictionaries with pattern matches and metrics.

        Note:
            KATO requires at least 1 string in STM to generate predictions.
        """
        # Flatten short-term memory: [["a","b"],["c"]] -> ["a","b","c"]
        state = list(chain(*stm))

        # Generate predictions if we have at least 1 string in state
        # Single-symbol predictions use optimized fast path
        if len(state) >= 1 and self.predict and trigger_predictions:
            predictions = await self.predictPattern(state, stm_events=list(stm))

            # Most recent predictions, for the legacy unique_id-less retrieval path
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

    async def processEvents(self, current_unique_id: str) -> list[dict[str, Any]]:
        """Predict from the processor's own STM (legacy stateful form of predict_from)."""
        return await self.predict_from(self.STM, current_unique_id, self.trigger_predictions)

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

    def retire_patterns(self, pattern_names: list[str]) -> dict[str, Any]:
        """Tombstone a batch of this node's patterns.

        A pure delegate. The ported version also cleared self.predictions and
        self.future_potentials here, but those are node-level attributes shared by
        every session on this processor, so a session-scoped retire would have
        blanked another session's in-flight state. The endpoint re-filters its own
        session snapshot instead.
        """
        return self.superkb.redis_writer.retire_patterns(pattern_names)

    def un_retire_patterns(self, pattern_names: list[str]) -> dict[str, Any]:
        """Remove tombstones for a batch, making the patterns visible again."""
        return self.superkb.redis_writer.un_retire_patterns(pattern_names)

    async def purge_retired_patterns(
        self,
        pattern_names: Optional[list[str]] = None,
        max_patterns: int = 1000,
    ) -> dict[str, Any]:
        """Permanently delete retired patterns and reverse their contribution.

        Retirement hides a pattern; purge erases it. Each pattern walks its
        tombstone from 'retired' through 'prepared' and 'redis_cleaned' to
        'purged', and the order of the two stores is deliberate:

        **Redis first, ClickHouse second.** The Redis step is guarded and
        abortable -- it verifies the node still matches the snapshot and writes
        nothing if it does not -- while the ClickHouse delete is irreversible.
        Doing the reversible, abortable step first means a rejected purge costs
        nothing; the other order destroys the pattern data before discovering the
        purge should not have proceeded. (The ported implementation had it the
        other way round, with the ClickHouse delete before an unguarded Redis
        loop, so a mid-batch failure left counters permanently inflated for
        patterns whose rows were already gone.)

        An interrupted purge is resumable, never corrupting: a pattern is only
        marked 'purged' after both stores have confirmed it absent, and every
        earlier state is safe to retry. Calling this again finishes the job.

        Errors are isolated per pattern. One malformed or contended id reports
        itself as failed and the rest of the batch completes -- a batch of 500
        must not be lost to one bad entry.

        Args:
            pattern_names: Patterns to purge. Defaults to every retired pattern
                on this node that has not already been purged.
            max_patterns: Upper bound on one call, so a node with a large
                retirement backlog cannot hold a request open indefinitely.

        Returns:
            A report with 'status' ('completed', 'partial' or 'nothing_to_purge'),
            'purged', 'failed' (id -> reason) and 'remaining'.
        """
        redis_writer = self.superkb.redis_writer

        # A pattern learned moments ago may still be in ClickHouse's async insert
        # buffer and invisible to the snapshot read below. Without this drain its
        # symbol counts would be read as absent, the ALTER ... DELETE would not
        # match it, verification would agree it was gone, and the row would then
        # surface -- a resurrected pattern with counters already reversed.
        #
        # On the shared client, before any thread work starts.
        self.superkb.clickhouse_writer.ensure_visible(
            redis_writer.get_global_metadata().get('stats_version', 0)
        )

        # Every ClickHouse call below runs in a worker thread, so it cannot use
        # the shared client: clickhouse-connect clients are session-bound and
        # raise "Attempt to execute concurrent queries within the same session"
        # the moment the event loop serves another request that reaches
        # ClickHouse. A purge holds its client for seconds while it polls, which
        # makes that collision near-certain rather than theoretical -- it showed
        # up as a 500 on an unrelated request. Hence a dedicated client for the
        # duration, as clickhouse-connect itself advises, and no lock.
        purge_client = get_connection_manager().build_clickhouse_client()
        if purge_client is None:
            raise DataConsistencyError(
                resource_id=self.kb_id,
                consistency_type='clickhouse unavailable',
                expected_value='a ClickHouse connection for the purge',
                actual_value='none could be created',
            )
        clickhouse_writer = ClickHouseWriter(self.kb_id, purge_client)
        try:
            return await self._run_purge(
                redis_writer, clickhouse_writer, pattern_names, max_patterns
            )
        finally:
            try:
                purge_client.close()
            except Exception as e:
                logger.debug(f"Closing the purge ClickHouse client failed: {e}")

    async def _run_purge(
        self,
        redis_writer,
        clickhouse_writer,
        pattern_names: Optional[list[str]],
        max_patterns: int,
    ) -> dict[str, Any]:
        """The purge itself, with the stores it should use passed in.

        Split out so the dedicated ClickHouse client is closed on every exit path.
        """

        candidates, failed = await asyncio.to_thread(
            self._collect_purge_candidates, pattern_names, max_patterns
        )
        if not candidates and not failed:
            return {
                'status': 'nothing_to_purge',
                'purged': [], 'failed': {}, 'remaining': 0,
            }

        # Phase 1 -- per pattern, in Redis: snapshot, then reverse.
        cleaned: list[str] = []
        for name in candidates:
            try:
                await asyncio.to_thread(
                    self._purge_one_from_redis, name, clickhouse_writer
                )
                cleaned.append(name)
            except Exception as e:
                # Isolated deliberately: a stale snapshot or a contended pattern
                # must not abort the patterns after it in the batch. The tombstone
                # is left wherever it got to, and all of those states are
                # resumable by calling this again.
                logger.warning(f"Redis purge phase failed for {name}: {e}")
                failed[name] = str(e)

        # Phase 2 -- one batched ClickHouse mutation for everything that reached
        # 'redis_cleaned', then wait for it to apply. A failure here leaves those
        # patterns at that state, which the next call resumes; nothing is marked
        # 'purged'.
        purged: list[str] = []
        if cleaned:
            try:
                await asyncio.to_thread(clickhouse_writer.purge_patterns, cleaned)
            except Exception as e:
                logger.error(f"ClickHouse purge failed for {len(cleaned)} pattern(s): {e}")
                for name in cleaned:
                    failed[name] = f"clickhouse delete failed: {e}"
                cleaned = []

        if cleaned:
            # The mutation applies in the background, so read the rows back rather
            # than trusting the submission. Anything still readable is reported as
            # unconfirmed and left resumable -- its delete is queued and will
            # complete, so a later call marks it purged.
            unconfirmed = await asyncio.to_thread(
                clickhouse_writer.wait_until_absent, cleaned
            )
            for name in unconfirmed:
                failed[name] = (
                    'deletion is still being applied; re-run the purge to confirm it'
                )
            cleaned = [name for name in cleaned if name not in set(unconfirmed)]

        # Phase 3 -- verify, then mark purged. The two stores are checked
        # independently of what they reported, because 'purged' is the point of no
        # return: the tombstone's snapshot is dropped there, so a pattern marked
        # purged while a record of it survives can never have its counters
        # replayed.
        if cleaned:
            purged, verification_failures = await asyncio.to_thread(
                self._verify_and_mark_purged, cleaned, clickhouse_writer
            )
            failed.update(verification_failures)

        if purged:
            # Once per batch, not per pattern: this is a whole-partition mutation.
            await asyncio.to_thread(clickhouse_writer.invalidate_precomputed_metrics)
            # On the event loop thread, not in a worker: this mutates searcher
            # state the loop may be reading for another session's prediction, and
            # it is pure in-memory dict work with nothing to block on.
            self._drop_purged_from_local_caches(purged)

        remaining = await asyncio.to_thread(self._count_unpurged, redis_writer)

        return {
            'status': 'completed' if not failed else 'partial',
            'purged': purged,
            'failed': failed,
            'remaining': remaining,
        }

    @staticmethod
    def _count_unpurged(redis_writer) -> int:
        """Retired patterns still awaiting a purge, for the caller's progress."""
        all_retired = redis_writer.get_retired_pattern_ids()
        if not all_retired:
            return 0
        records = redis_writer.get_retirement_records(list(all_retired))
        return sum(
            1 for record in records.values() if record.get('state') != 'purged'
        )

    def _collect_purge_candidates(
        self, pattern_names: Optional[list[str]], max_patterns: int
    ) -> tuple[list[str], dict[str, str]]:
        """Resolve the batch: retired, not already purged, and well-formed.

        Validation happens here rather than at the edge as well, because this is
        also reachable with no explicit list at all. Rejected ids are reported,
        not raised: the caller gets a per-id reason and the rest of the batch
        proceeds.
        """
        redis_writer = self.superkb.redis_writer
        failed: dict[str, str] = {}

        if pattern_names is None:
            requested = sorted(redis_writer.get_retired_pattern_ids())
        else:
            requested = []
            for name in pattern_names:
                try:
                    requested.append(redis_writer.normalize_pattern_name(name))
                except (TypeError, ValueError) as e:
                    failed[str(name)] = str(e)
            # De-duplicate but keep the caller's order, so a repeated id is not
            # prepared twice within one batch.
            requested = list(dict.fromkeys(requested))

        if not requested:
            return [], failed

        records = redis_writer.get_retirement_records(requested)
        candidates: list[str] = []
        for name in requested:
            record = records.get(name)
            if record is None:
                failed[name] = 'not retired'
            elif record.get('state') == 'purged':
                # Already done. Not a failure.
                continue
            else:
                candidates.append(name)

        return candidates[:max_patterns], failed

    def _purge_one_from_redis(self, name: str, clickhouse_writer) -> None:
        """Snapshot one pattern's contribution, then reverse it. Raises on refusal."""
        redis_writer = self.superkb.redis_writer

        records = redis_writer.get_retirement_records([name])
        state = records.get(name, {}).get('state')

        if state in ('redis_cleaned', 'purged'):
            return  # Resuming a partial purge; Redis is already settled.

        if state != 'prepared':
            stored = clickhouse_writer.get_pattern_data(name)
            symbol_counts = (
                dict(Counter(chain(*stored['pattern_data']))) if stored else {}
            )
            snapshot = redis_writer.build_purge_snapshot(
                name, symbol_counts,
                self._resolve_affinity_contribution(name),
            )

            # The symbol counts come from the stored pattern, so a missing
            # ClickHouse row leaves nothing to subtract per symbol -- while the
            # live Redis frequency key says the pattern did contribute. Purging
            # on that snapshot would decrement the two global pattern counters
            # and leave symbols:freq, symbols:pmf, the symbol indices and
            # affinity inflated for every symbol it held, with the tombstone
            # marked 'purged' and its snapshot discarded, so nothing could ever
            # reconstruct the difference.
            #
            # Refuse instead, and say which store is missing what. The index
            # cannot stand in: symbol_to_patterns records that a symbol appears
            # in the pattern, not how many times, and the reversal needs the
            # multiplicity. Resolve it by restoring the row or, if the pattern is
            # genuinely gone from ClickHouse, by un-retiring and re-learning it so
            # both stores agree before purging again.
            if snapshot['had_pattern_record'] and not symbol_counts:
                raise DataConsistencyError(
                    resource_id=name,
                    consistency_type='missing patterns_data row',
                    expected_value='a patterns_data row to read symbol counts from',
                    actual_value='no row, but Redis still holds its frequency counter',
                    message=(
                        f"Cannot purge {name}: its patterns_data row is missing "
                        f"while Redis still holds its frequency counter, so there "
                        f"is no way to reverse its per-symbol contribution. Restore "
                        f"the row, or un-retire and re-learn the pattern so both "
                        f"stores agree."
                    ),
                    context={'kb_id': self.kb_id},
                )
            outcome = redis_writer.prepare_pattern_purge(name, snapshot)
            if outcome == 'not_retired':
                raise ValueError(f"pattern {name} is not retired")

        outcome = redis_writer.purge_pattern_records(name)
        if outcome == 'not_retired':
            raise ValueError(f"pattern {name} is not retired")

    def _resolve_affinity_contribution(self, name: str) -> dict[str, float]:
        """What this pattern added to per-symbol affinity, exactly or approximately.

        Affinity sums *averaged* emotives, and the average moves with the rolling
        persistence window on every learn, so nothing in the stored pattern
        recovers the figure. The ledger written at learn time is the exact record.

        Patterns learned before the ledger existed have none, and for those there
        is a choice between leaving their contribution behind forever and
        subtracting a best estimate. The estimate is used: a pattern learned once,
        with its emotives still inside the persistence window, has a current
        average identical to what it contributed, so the estimate is exact; beyond
        that it is approximate, and an approximate reversal is closer to the truth
        than none. It is subtracted through the same clamped arithmetic as any
        other, so an over-estimate cannot drive a shared symbol's affinity
        negative -- it clamps at zero and the field is removed.
        """
        redis_writer = self.superkb.redis_writer

        ledger = redis_writer.get_affinity_ledger(name)
        if ledger is not None:
            return ledger

        metadata = self.superkb.metadata_router.get_metadata_for_merge(name)
        emotives = metadata.get('emotives') or []
        if not emotives:
            return {}

        averaged = average_emotives(emotives)
        frequency = redis_writer.get_frequency(name)
        exact = frequency == 1 and len(emotives) <= self.superkb.persistence

        if exact:
            estimate = averaged
        else:
            # Each learn contributed one average; frequency learns contributed
            # frequency of them. The window may have discarded older values, so
            # this is the closest reconstruction available.
            estimate = {
                name_: value * max(frequency, 1)
                for name_, value in averaged.items()
            }

        logger.info(
            f"No affinity ledger for pattern {name} (learned before the ledger "
            f"existed); reversing {'an exact' if exact else 'an estimated'} "
            f"contribution derived from {len(emotives)} retained emotive "
            f"record(s) and frequency={frequency}"
        )
        return estimate

    def _verify_and_mark_purged(
        self, names: list[str], clickhouse_writer
    ) -> tuple[list[str], dict[str, str]]:
        """Confirm both stores are clear of each pattern, then mark it purged."""
        redis_writer = self.superkb.redis_writer

        # wait_until_absent has already confirmed these rows are unreadable. This
        # drain covers the other direction: a row that was still in the async
        # insert queue when the mutation evaluated its predicate, and so was never
        # a candidate for deletion, but lands afterwards and becomes queryable.
        clickhouse_writer.flush_async_insert_queue()

        purged: list[str] = []
        failed: dict[str, str] = {}

        still_in_clickhouse = set(clickhouse_writer.patterns_still_present(names))
        for name in names:
            leftovers = redis_writer.verify_pattern_records_absent(name)
            if name in still_in_clickhouse:
                leftovers = leftovers + ['clickhouse row']
            if leftovers:
                # Left at 'redis_cleaned' on purpose, so the next call retries.
                failed[name] = f"records survived purge: {', '.join(leftovers)}"
                continue
            redis_writer.mark_pattern_purged(name)
            purged.append(name)

        return purged, failed

    def _drop_purged_from_local_caches(self, names: list[str]) -> None:
        """Release purged patterns held by this worker's in-memory caches.

        Hygiene, not correctness. FilterPipelineExecutor.patterns_cache is built
        once per searcher and only ever added to, so without this a long-lived
        worker holds every purged pattern's data for its whole life. It is
        unreachable either way: candidates come from ClickHouse, where the rows
        are gone, and the tombstone survives the purge so the read-side filter
        would drop them regardless.

        Only this worker's caches -- other uvicorn workers keep their own copies
        until they restart, which is harmless for the same two reasons.
        """
        searcher = getattr(self, 'patterns_searcher', None)
        if searcher is None:
            return

        executor = getattr(searcher, 'filter_executor', None)
        for name in names:
            if executor is not None:
                executor.patterns_cache.pop(name, None)
            try:
                searcher.delete_pattern(name)
            except Exception as e:
                logger.debug(f"Local cache eviction for {name} failed: {e}")


    def filter_retired_predictions(self, predictions: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Drop predictions for patterns this node has retired.

        For the paths that do not go through PatternSearcher: the single-symbol
        fast path, which queries patterns_data directly, and retrieval of a stored
        prediction snapshot, which may have been computed before the retirement.

        Costs one EXISTS on a node with no tombstones. Subtractive, and order
        among survivors is preserved.
        """
        if not predictions:
            return predictions
        names = [
            prediction.get('name')
            for prediction in predictions
            if isinstance(prediction, dict) and prediction.get('name')
        ]
        if not names:
            return predictions

        retired = self.superkb.redis_writer.get_retired_pattern_ids(names)
        if not retired:
            return predictions

        def is_active(prediction):
            name = prediction.get('name') or ''
            clean = name[5:] if name.startswith('PTRN|') else name
            return clean not in retired

        return [prediction for prediction in predictions if is_active(prediction)]

    async def _single_symbol_candidates(
        self, symbol: str, stm_events: Optional[list[list[str]]] = None
    ) -> list[Any]:
        """Select candidate patterns for a single-symbol state, cheaply.

        This is the fast path, and it is now only a *selection* step. It skips the
        filter pipeline -- the expensive part -- by reading patterns whose
        `first_token` is this symbol straight out of ClickHouse, then builds the
        same `Prediction` objects the searcher builds. Everything after selection
        (metadata, metrics, potential, ranking) is the shared tail in
        predictPattern, so the two paths cannot disagree.

        It used to compute its own metrics and return, which left single-symbol
        predictions missing fourteen fields the normal path returns
        (`predictive_information`, `confluence`, `entropy`, the three `bayesian_*`,
        `itfdf_similarity`, `tfidf_score`, `pattern_probability`,
        `normalized_entropy`, `global_normalized_entropy`, `weighted_strength`,
        `type`, `sequence`) and, worse, disagreeing on three it did return:
        `snr` used `m/(m+x)` where Prediction uses `(2m-x)/(2m+x)`, `evidence`
        divided by a different length, and `potential` omitted the
        `itfdf_similarity` term -- so the ranking key itself was not comparable
        between paths. A client reading any of the fourteen got a KeyError for a
        one-symbol STM and a value for a two-symbol one.

        Returns:
            Unranked Prediction objects with placeholder frequency/emotives, ready
            for the shared tail. Empty list if nothing starts with this symbol.
        """
        logger.info(f"*** {self.name} [ PatternProcessor single-symbol candidate selection symbol='{symbol}' ]")

        # Visibility is handled by predictPattern, this function's only caller,
        # which calls ensure_visible before dispatching here. This path queries
        # patterns_data directly, so it is the one most exposed to the async
        # insert window -- the observed miss was on this query.
        from kato.storage.connection_manager import get_clickhouse_client
        clickhouse_client = get_clickhouse_client()
        if not clickhouse_client:
            logger.warning("ClickHouse not available; cannot select single-symbol candidates")
            return []

        # Uses the first_token column (populated during _prepare_row) instead of
        # building a large IN-clause from Redis, which overflows max_query_size at scale.
        result = clickhouse_client.query(
            """
            SELECT name, pattern_data, length
            FROM kato.patterns_data
            WHERE kb_id = %(kb_id)s AND first_token = %(first_token)s
            """,
            parameters={'kb_id': self.superkb.id, 'first_token': symbol},
        )
        if not result.result_rows:
            logger.debug(f"No patterns found starting with symbol '{symbol}'")
            return []

        candidate_patterns = [
            {'name': name, 'pattern_data': pattern_data, 'length': length}
            for name, pattern_data, length in result.result_rows
            if pattern_data and pattern_data[0] and pattern_data[0][0] == symbol
        ]
        if not candidate_patterns:
            logger.debug(f"No patterns START with symbol '{symbol}' (found patterns containing it)")
            return []

        logger.debug(f"Found {len(candidate_patterns)} patterns STARTING with symbol '{symbol}'")

        from kato.searches.pattern_search import InformationExtractor
        extractor = InformationExtractor(
            use_fast_matcher=True,
            use_token_matching=self.use_token_matching
        )
        state = [symbol]

        # Every candidate already starts with this symbol, so the recall threshold
        # has nothing left to exclude.
        single_symbol_threshold = 0.0

        weights = self._compute_affinity_weights(state, candidate_patterns)
        # The shared tail reads weights from the searcher, as the normal path does.
        self.patterns_searcher.affinity_weights = weights

        def _build(batch):
            """Build Prediction objects for a batch of candidates (thread-safe)."""
            built = []
            for pattern_dict in batch:
                prediction_info = extractor.extract_prediction_info(
                    list(chain(*pattern_dict['pattern_data'])),
                    state,
                    cutoff=single_symbol_threshold,
                    fuzzy_token_threshold=0.0,
                    weights=weights
                )
                if not prediction_info:
                    continue

                (_pattern, matching_intersection, past, present, missing, extras,
                 similarity, number_of_blocks, anomalies, weighted_similarity,
                 alignment) = prediction_info[:11]

                # Placeholder frequency/emotives, exactly as the searcher does:
                # attach_pattern_metadata fills them for the survivors of pruning,
                # and nothing before that point reads them.
                built.append(Prediction(
                    {
                        'name': pattern_dict['name'],
                        'pattern_data': pattern_dict['pattern_data'],
                        'length': pattern_dict['length'],
                        'frequency': 1,
                        'emotives': {},
                    },
                    matching_intersection,
                    past, present,
                    missing,
                    extras,
                    similarity,
                    number_of_blocks,
                    fuzzy_matches=anomalies,
                    stm_events=stm_events,
                    weighted_similarity=weighted_similarity,
                    alignment=alignment,
                ))
            return built

        SINGLE_SYMBOL_PARALLEL_THRESHOLD = 100
        if len(candidate_patterns) > SINGLE_SYMBOL_PARALLEL_THRESHOLD:
            import concurrent.futures
            import multiprocessing
            max_workers = min(multiprocessing.cpu_count(), 8)
            batch_sz = max(1, len(candidate_patterns) // max_workers)
            batches = [candidate_patterns[i:i + batch_sz]
                       for i in range(0, len(candidate_patterns), batch_sz)]
            predictions = []
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = [executor.submit(_build, b) for b in batches]
                for future in concurrent.futures.as_completed(futures):
                    predictions.extend(future.result())
        else:
            predictions = _build(candidate_patterns)

        logger.debug(f"Selected {len(predictions)} single-symbol candidates for '{symbol}'")
        return predictions


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

        # Make patterns learned since the last drain queryable before anything
        # below reads patterns_data. This is the only entry point for predictions
        # -- including the single-symbol fast path -- so one gate here covers them
        # all.
        #
        # This replaced a flush_if_pending() call that read as "make recent writes
        # visible" but drained only the CLIENT buffer, permanently empty at
        # batch_size=1, and so did nothing. The row lives in ClickHouse's
        # server-side async buffer until it flushes, and under load that delay
        # grows toward async_insert_busy_timeout_max_ms: observed here as the fast
        # path logging "No patterns found" for a symbol and, 182ms later, "Found 1
        # patterns", with nothing changed but time.
        #
        # The read is three integers in one MGET, and the drain is skipped unless
        # a learn has landed since the last one -- see ensure_visible.
        self.superkb.clickhouse_writer.ensure_visible(
            self.superkb.redis_writer.get_global_metadata().get('stats_version', 0)
        )

        # future_potentials is cleared before either selection strategy runs. A
        # processor is shared by every session on a node, so a request that
        # returns before the ensemble predictive-information pass would otherwise
        # leave the previous request's value in place and the endpoint would serve
        # ANOTHER SESSION's future_potentials — observed live as a query answering
        # with 0 predictions but 2 future_potentials belonging to a different
        # session.
        self.future_potentials = []

        # Candidate selection. Single-symbol states take the cheap path, which
        # skips the filter pipeline; everything after this point is shared, so the
        # two strategies produce predictions of the same shape with the same
        # metrics. Selection is the only thing that differs.
        try:
            if len(state) == 1:
                logger.info("Using single-symbol candidate selection for state=%s", state)
                causal_patterns = await self._single_symbol_candidates(
                    state[0], stm_events=stm_events)
            else:
                # Compute and set affinity weights on pattern searcher before matching
                self.patterns_searcher.affinity_weights = self._compute_affinity_weights(state)

                # Use async parallel pattern matching
                causal_patterns = await self.patterns_searcher.causalBeliefAsync(
                    state, self.target_class_candidates, stm_events, max_workers, batch_size)
        except Exception as e:
            raise Exception(f"\nException in PatternProcessor.predictPattern: Error in candidate selection! {self.kb_id}: {e}")

        # Retirement barrier, for both selection strategies and before any
        # pruning or ranking. A retired pattern must not occupy one of the
        # max_predictions slots and then be dropped, which would return fewer
        # predictions than asked for while active patterns went unreported.
        #
        # The searcher already filters its own candidates, so for the normal path
        # this is a second pass that finds nothing; on a node with no tombstones
        # it costs one Redis EXISTS against a key that does not exist. The
        # single-symbol path has no searcher stage to filter in, and this used to
        # be done inside it -- keeping it here is what makes the guarantee hold
        # for both.
        causal_patterns = self.filter_retired_predictions(causal_patterns)

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
            # Same total order as the final ranking: ties here decide which
            # candidates even reach the metrics loop, so settling them by
            # arrival order would make the final result non-deterministic too.
            causal_patterns = rank_predictions(
                causal_patterns, '_pre_potential', max_for_metrics
            )
            logger.debug(f"Top-K pruning: kept {len(causal_patterns)} of {original_count} candidates for metrics loop")

        # Now that the list is cut to its final size, fetch the pattern metadata.
        # The searcher builds predictions with placeholder frequency/emotives
        # precisely so this can happen here: fetching before the prune meant a
        # ClickHouse+Redis lookup for every pattern that matched -- the whole
        # node under the default empty filter_pipeline -- to populate two fields
        # on a list about to be cut to max_predictions * 3. That cost scaled with
        # the corpus; this does not. Everything that reads frequency or emotives
        # (total_ensemble_pattern_frequencies, patternProbability,
        # itfdf_similarity, average_emotives, the Bayesian priors) runs below
        # this line.
        # Also returns the precomputed entropy/tf metrics from the same rows,
        # so the second read of patterns_metadata below is no longer needed.
        precomputed_metrics = self.patterns_searcher.attach_pattern_metadata(causal_patterns)

        try:
            # Pre-calculate symbol probability cache using optimized aggregation pipeline
            symbol_probability_cache = {}
            total_ensemble_pattern_frequencies = 0

            # Read the global counters fresh on every prediction, rather than
            # memoising them per process. They are three small integers in one
            # MGET, and caching them was a source of cross-worker divergence:
            # the cache was dropped only when THIS process learned, so a worker
            # that missed the learn served stale totals indefinitely. The same
            # MGET also returns stats_version, which tells the (genuinely
            # expensive) symbol table whether another process changed the data.
            global_metadata = self.superkb.redis_writer.get_global_metadata()
            total_pattern_frequencies = global_metadata.get('total_pattern_frequencies', 0)
            total_unique_patterns = global_metadata.get('total_unique_patterns', 1)  # Use 1 to avoid div by zero
            stats_version = global_metadata.get('stats_version', 0)

            # Load all symbols (cached by QueryManager, validated against the
            # version above so a write from another worker invalidates it too).
            symbol_cache = self.query_manager.get_all_symbols_optimized(
                self.superkb.symbols_kb, stats_version=stats_version
            )
            total_symbols = len(symbol_cache)
            logger.debug(f"Loaded {total_symbols} symbols using optimized aggregation pipeline (async)")

            def _corpus_probability(symbol: str) -> float:
                """Probability that a random pattern contains `symbol`."""
                symbol_data = symbol_cache.get(symbol)
                if symbol_data is None or total_unique_patterns <= 0:
                    return 0.0
                return float(symbol_data['pattern_member_frequency'] / total_unique_patterns)

            # Calculate totals and caches
            for prediction in causal_patterns:
                total_ensemble_pattern_frequencies += prediction['frequency']
                # Flatten missing if it's event-structured (list of lists)
                missing_symbols_calc = prediction['missing']
                if missing_symbols_calc and isinstance(missing_symbols_calc[0], list):
                    missing_symbols_calc = [s for event in missing_symbols_calc for s in event]
                for symbol in itertools.chain(prediction['matches'], missing_symbols_calc):
                    if symbol not in symbol_probability_cache:
                        # total_unique_patterns, not total frequency: pattern-based
                        # probability, in units compatible with pattern_member_frequency.
                        symbol_probability_cache[symbol] = _corpus_probability(symbol)

            symbol_frequency_in_state = Counter(state)

            if total_ensemble_pattern_frequencies == 0:
                logger.warning(f" {self.name} [ PatternProcessor predictPattern (async) ] total_ensemble_pattern_frequencies is 0")

            # Pre-computed pattern-intrinsic metrics (entropy, normalized_entropy,
            # global_normalized_entropy, tf_vector) came back with the metadata
            # attached above. They live in the same patterns_metadata rows and
            # the same query already selected them, so reading them here a second
            # time was a duplicate round trip for information already in hand.
            precomputed_hit = len(precomputed_metrics)
            precomputed_miss = len(causal_patterns) - precomputed_hit
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
                    # Fallback: compute at runtime (pattern predates finalize-training).
                    # These are pattern-intrinsic, so they are computed over the
                    # whole pattern exactly as finalize_training does -- not over
                    # `present`, which is only the matched events and gave the same
                    # pattern a different value before and after finalization.
                    pattern_symbols = [s for event in prediction['pattern_data'] for s in event]
                    pattern_length = len(pattern_symbols)
                    if pattern_symbols:
                        symbol_counts = Counter(pattern_symbols)
                        # Shannon entropy (log base 2)
                        entropy_val = 0.0
                        for count in symbol_counts.values():
                            if count > 0:
                                p = count / pattern_length
                                entropy_val -= p * log2(p)
                        normalized_entropy_val = normalized_entropy(pattern_symbols, total_symbols)
                        # Not symbol_probability_cache: that holds only matched and
                        # missing symbols, so past/future symbols would read as 0.
                        # finalize_training uses the whole symbol table; so must this.
                        pattern_probabilities = {
                            symbol: _corpus_probability(symbol) for symbol in set(pattern_symbols)
                        }
                        global_normalized_entropy_val = global_normalized_entropy(
                            pattern_symbols, pattern_probabilities, total_symbols
                        )
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
                    # Fallback: compute TF and IDF at runtime, over the whole
                    # pattern to match the pre-computed tf_vector.
                    if not precomp:
                        pattern_symbols = [s for event in prediction['pattern_data'] for s in event]
                    else:
                        pattern_symbols = []  # precomp exists but total_unique_patterns == 0
                    # Counter, not repeated list.count(): counting each unique
                    # symbol by rescanning the list is O(n^2) in pattern length.
                    symbol_counts = Counter(pattern_symbols)
                    pattern_length = len(pattern_symbols)

                    if pattern_length > 0 and total_unique_patterns > 0:
                        tfidf_scores = []
                        for symbol, symbol_count in symbol_counts.items():
                            tf = symbol_count / pattern_length
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
                # Rank using the configurable algorithm (default: 'potential').
                # rank_predictions tie-breaks on the pattern name, which is what
                # makes repeated identical requests return the same predictions
                # in the same order -- see its docstring.
                active_causal_patterns = rank_predictions(
                    causal_patterns, self.rank_sort_algo, self.max_predictions
                )
            except KeyError:
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
