import asyncio
import logging
from collections import Counter, OrderedDict, deque
from itertools import chain
from math import log2
from os import environ
from typing import Any, NamedTuple, Optional

from kato.config.session_config import SessionConfiguration
from kato.exceptions import DataConsistencyError
from kato.informatics.knowledge_base import SuperKnowledgeBase
from kato.informatics.metrics import (
    accumulate_metadata,
    average_emotives,
    global_normalized_entropy,
    normalized_entropy,
)
from kato.informatics.prediction_metrics import (
    NodeStatistics,
    Observation,
    confluence,
    itfdf_similarity,
    score_ensemble,
    tfidf_score,
)
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


# Most sessions a processor keeps a searcher for. A cached searcher holds only
# its configuration between requests (release_request_data drops what a request
# loaded), so an entry is small; the bound is for sessions that end without
# being deleted.
SESSION_SEARCHER_CACHE_SIZE = 1024

# Pattern names per MGET when the candidates' frequencies are read. A request
# can have tens of thousands of candidates; one MGET of that size holds Redis,
# which serves one command at a time, for the whole of it.
FREQUENCY_BATCH_SIZE = 5000

# Metrics that predictPattern works out after ranking, for the predictions it
# returns: each describes one prediction (most of them the pattern alone) and
# needs nothing from the other candidates but a total that is already known. A
# session that ranks by one of them gets it worked out for every candidate
# first, so the ranking is over all of them.
PATTERN_METRICS = frozenset({
    'entropy', 'normalized_entropy', 'global_normalized_entropy',
    'tfidf_score', 'itfdf_similarity', 'confluence',
})


class PredictionSettings(NamedTuple):
    """A session's prediction settings, read from its stored configuration.

    A processor is shared by every session on a node, so the predict path takes
    these as an argument rather than reading them from the processor. Setting
    them on the processor -- as get_predictions_async used to, swapping the
    searcher and max_predictions around an await -- let a concurrent request on
    the same node run with another session's settings.
    """
    searcher: PatternSearcher
    max_predictions: int
    rank_sort_algo: str
    use_token_matching: bool


class PredictionResult(NamedTuple):
    """One request's predictions and the figures computed over its whole ensemble.

    future_potentials and chance_posterior are ensemble figures, so they come
    back with the predictions they were computed from rather than being left on
    the processor. A processor is shared by every session on a node: when
    future_potentials was kept there, the predictions endpoint read it back
    after the request, and a request that computed none -- an empty STM returns
    before predicting -- served the previous request's value, which could be
    another session's.

    chance_posterior is the probability that no learned pattern explains the
    STM better than chance: what the candidates' bayesian_posterior values
    leave over. It is 1.0 when no pattern reached the recall threshold and
    None when no prediction was attempted (an empty STM, or predictions read
    back by unique_id).
    """
    predictions: list[dict[str, Any]]
    future_potentials: list[dict[str, Any]]
    chance_posterior: Optional[float] = None


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
        # Per-session searchers, built from each session's stored configuration and
        # reused until that configuration changes. See _prediction_settings.
        self._session_searchers: OrderedDict[str, tuple[str, PatternSearcher]] = OrderedDict()
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
        becomes of it afterwards (cleared or rolled). Creates a
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
        # Frequency lives in Redis only. Dropping it takes this pattern's
        # learns out of total_pattern_frequencies in the same step.
        self.superkb.redis_writer.set_frequency(name, 0)
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
        # total_pattern_frequencies moves by the difference in the same step.
        self.superkb.redis_writer.set_frequency(name, frequency)
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
        config: Optional[SessionConfiguration] = None,
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
            config: The session's configuration. Its prediction settings
                (recall_threshold, max_predictions, use_token_matching,
                rank_sort_algo, and the searcher's session settings) apply to
                this request; None uses the node defaults.

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
            predictions = (await self._predict_with_config(state, list(stm), config)).predictions

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

    def _compute_affinity_weights(
        self,
        state: list[str],
        candidate_patterns: list[dict] = None,
        searcher: Optional[PatternSearcher] = None,
    ) -> Optional[dict[str, float]]:
        """
        Compute affinity-weighted token weights for pattern matching.

        Uses frequency-normalized absolute affinity: w(t) = |aff(t, e)| / freq(t) + epsilon

        Args:
            state: Flattened STM state tokens
            candidate_patterns: Optional list of candidate pattern dicts (for single-symbol path).
                If None, weights are computed only for state tokens (pattern tokens
                will get floor weight if not in the weight map).
            searcher: The request's searcher, which carries its session
                configuration. Defaults to the processor's own searcher.

        Returns:
            Dict mapping symbol -> weight, or None if affinity weighting is not active.
        """
        # Check if affinity_emotive is configured (session_config lives on the PatternSearcher)
        affinity_emotive = None
        searcher = searcher or getattr(self, 'patterns_searcher', None)
        if searcher:
            sc = getattr(searcher, 'session_config', None)
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

        A pure delegate. The ported version also cleared self.predictions here,
        but that is a node-level attribute shared by every session on this
        processor, so a session-scoped retire would have blanked another
        session's in-flight state. The endpoint re-filters its own
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


    def _attach_frequencies(self, predictions: list[dict[str, Any]]) -> None:
        """Read the frequency of every given prediction's pattern, in place.

        Frequency lives in Redis, one key per pattern, so this is an MGET per
        FREQUENCY_BATCH_SIZE names and no ClickHouse query.

        A pattern with no frequency recorded keeps 1: it was found in
        ClickHouse, so it was learned at least once, and a missing or zero
        counter means the Redis record was lost, not that the pattern was
        unlearned.
        """
        names = [prediction['name'] for prediction in predictions]
        frequencies: dict[str, int] = {}
        for start in range(0, len(names), FREQUENCY_BATCH_SIZE):
            frequencies.update(
                self.superkb.redis_writer.get_frequency_batch(names[start:start + FREQUENCY_BATCH_SIZE]))

        unrecorded = 0
        for prediction in predictions:
            frequency = frequencies.get(prediction['name'], 0)
            if frequency < 1:
                unrecorded += 1
                frequency = 1
            prediction['frequency'] = frequency
        if unrecorded:
            logger.warning(
                "%d of %d candidate patterns of %s have no frequency in Redis "
                "-- possible Redis data loss. Counting each as learned once.",
                unrecorded, len(predictions), self.kb_id,
            )

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
        self,
        symbol: str,
        settings: PredictionSettings,
        stm_events: Optional[list[list[str]]] = None,
    ) -> list[Any]:
        """Select candidate patterns for a single-symbol state, cheaply.

        This is the fast path, and it is now only a *selection* step. It skips the
        filter pipeline -- the expensive part -- by reading patterns that contain
        this symbol, in any event, straight out of ClickHouse, then builds the
        same `Prediction` objects the searcher builds.

        It used to read only patterns whose `first_token` was the symbol. Events
        are sorted, so that made eligibility depend on alphabetical order: of
        [['A','B','C'], ['marker']], a lone 'A' matched and a lone 'B' did not
        (issue #15). Preferring patterns that start with the observed symbols is
        a ranking concern, not a selection filter: `potential` scores a pattern
        higher the less of it lies before the match (`evidence_to_end`), and
        `onset_alignment` reports the position. Everything after selection
        (frequencies, scores, ranking, metadata, metrics) is the shared tail in
        predictPattern, so the two paths cannot disagree.

        It used to compute its own metrics and return, which left single-symbol
        predictions missing fields the normal path returns and, worse,
        disagreeing on three it did return: `snr` used `m/(m+x)` where
        Prediction uses `(2m-x)/(2m+x)`, `evidence` divided by a different
        length, and `potential` left out a term -- so the ranking key itself was
        not comparable between paths. A client reading one of the missing
        fields got a KeyError for a one-symbol STM and a value for a two-symbol
        one.

        Returns:
            Unranked Prediction objects with placeholder frequency/emotives, ready
            for the shared tail. Empty list if no pattern contains this symbol.
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

        # Filters on token_set, which carries the idx_token_bloom skip index, in
        # ClickHouse rather than building a large IN-clause from Redis, which
        # overflows max_query_size at scale.
        result = clickhouse_client.query(
            """
            SELECT name, pattern_data, length
            FROM kato.patterns_data
            WHERE kb_id = %(kb_id)s AND has(token_set, %(symbol)s)
            """,
            parameters={'kb_id': self.superkb.id, 'symbol': symbol},
        )
        candidate_patterns = [
            {'name': name, 'pattern_data': pattern_data, 'length': length}
            for name, pattern_data, length in result.result_rows
            if pattern_data
        ]
        if not candidate_patterns:
            logger.debug(f"No patterns found containing symbol '{symbol}'")
            return []

        logger.debug(f"Found {len(candidate_patterns)} patterns containing symbol '{symbol}'")

        from kato.searches.pattern_search import InformationExtractor
        extractor = InformationExtractor(
            use_fast_matcher=True,
            use_token_matching=settings.use_token_matching
        )
        state = [symbol]

        # Every candidate contains this symbol, so it matches. The recall threshold
        # is not applied: one symbol against a long pattern has a similarity below
        # the default threshold, and this path has always returned such patterns.
        single_symbol_threshold = 0.0

        weights = self._compute_affinity_weights(state, candidate_patterns, settings.searcher)
        # The shared tail reads weights from the searcher, as the normal path does.
        settings.searcher.affinity_weights = weights

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
                # predictPattern reads the frequency of every candidate before
                # it scores them and the emotives of the ones it returns.
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


    async def predictPattern(self, state: list[str], stm_events: Optional[list[list[str]]] = None, max_workers: Optional[int] = None, batch_size: int = 100, settings: Optional[PredictionSettings] = None) -> PredictionResult:
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

        Scoring order:
        - Every candidate above the recall threshold gets its frequency, then
          the scores that need the whole ensemble (prediction_metrics.score_ensemble).
        - The candidates are ranked by the settings' rank_sort_algo and cut to
          max_predictions.
        - The metrics that describe one prediction at a time (PATTERN_METRICS)
          and the pattern's emotives are worked out for what is returned.
        Nothing is cut before it is scored, so no returned value depends on
        max_predictions.

        Args:
            state: Flattened list of symbols representing current STM state.
            stm_events: The STM's events, as the session holds them. None reads
                `state` as a single event.
            max_workers: Maximum number of worker threads (defaults to CPU count)
            batch_size: Number of patterns per batch for parallel processing
            settings: This request's settings, from _prediction_settings. None
                uses the node defaults. Everything below reads the searcher,
                max_predictions and rank_sort_algo from here, never from self.

        Returns:
            PredictionResult: the prediction dictionaries, ranked by the
            settings' rank_sort_algo and carrying their metrics; the future
            potentials (the probability of each next event) and the chance
            posterior, both computed over every candidate.

        Raises:
            Exception: If async pattern search fails.
            ValueError: If predictions are missing required fields.
        """
        logger.info(f"*** {self.name} [ PatternProcessor predictPattern (async) called with state={state} ]")

        if settings is None:
            settings = self._prediction_settings(None)
        searcher = settings.searcher

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

        # Candidate selection. Single-symbol states take the cheap path, which
        # skips the filter pipeline; everything after this point is shared, so the
        # two strategies produce predictions of the same shape with the same
        # metrics. Selection is the only thing that differs.
        try:
            if len(state) == 1:
                logger.info("Using single-symbol candidate selection for state=%s", state)
                causal_patterns = await self._single_symbol_candidates(
                    state[0], settings, stm_events=stm_events)
            else:
                # Compute and set affinity weights on pattern searcher before matching
                searcher.affinity_weights = self._compute_affinity_weights(state, searcher=searcher)

                # Use async parallel pattern matching
                causal_patterns = await searcher.causalBeliefAsync(
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

        # Early return if no patterns found. No learned pattern reached the
        # recall threshold, so nothing competes with chance for this STM: the
        # chance posterior is 1.
        if not causal_patterns:
            logger.debug(f" {self.name} [ PatternProcessor predictPattern (async) ] No causal patterns found, returning empty list")
            return PredictionResult([], [], 1.0)

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
        weights = searcher.affinity_weights
        if weights:
            for p in causal_patterns:
                matches = p.get('matches', [])
                present_events = p.get('present', [])
                extras = p.get('extras', [])
                pattern_data = p.get('pattern_data', [])

                present_flat = list(chain(*present_events)) if present_events and isinstance(present_events[0], list) else (present_events or [])
                pattern_flat = list(chain(*pattern_data)) if pattern_data and isinstance(pattern_data[0], list) else (pattern_data or [])

                # Handle event-structured extras
                if extras and isinstance(extras[0], list):
                    extras_flat = list(chain(*extras))
                else:
                    extras_flat = extras or []

                w_matched = sum(weights.get(t, 0.0) for t in matches)
                w_pattern = sum(weights.get(t, 0.0) for t in pattern_flat)
                w_present = sum(weights.get(t, 0.0) for t in present_flat)
                w_extras = sum(weights.get(t, 0.0) for t in extras_flat)

                p['weighted_evidence'] = (w_matched / w_pattern) if w_pattern > 0 else 0.0
                p['weighted_confidence'] = (w_matched / w_present) if w_present > 0 else 0.0
                p['weighted_snr'] = (w_matched / (w_matched + w_extras)) if (w_matched + w_extras) > 0 else 0.0

        # Every candidate is scored before anything is cut. `potential` and the
        # prior need each pattern's frequency, and the posterior,
        # future_potentials and predictive_information are sums over all the
        # candidates: cut first, and their values depend on the cut and on
        # max_predictions. So the frequencies are read here, for all of them,
        # in chunked MGETs against Redis. The rest of a pattern's metadata
        # (emotives, the precomputed entropy and tf columns) is a ClickHouse
        # lookup per chunk of names and is read further down, for the
        # predictions that are returned.
        self._attach_frequencies(causal_patterns)

        try:
            # Read the global counters fresh on every prediction, rather than
            # memoising them per process. They are three small integers in one
            # MGET, and caching them was a source of cross-worker divergence:
            # the cache was dropped only when THIS process learned, so a worker
            # that missed the learn served stale totals indefinitely. The same
            # MGET also returns stats_version, which tells the (genuinely
            # expensive) symbol table whether another process changed the data.
            global_metadata = self.superkb.redis_writer.get_global_metadata()
            stats_version = global_metadata.get('stats_version', 0)

            # Load all symbols (cached by QueryManager, validated against the
            # version above so a write from another worker invalidates it too).
            symbol_cache = self.query_manager.get_all_symbols_optimized(
                self.superkb.symbols_kb, stats_version=stats_version
            )
            total_symbols = len(symbol_cache)
            logger.debug(f"Loaded {total_symbols} symbols using optimized aggregation pipeline (async)")

            node = NodeStatistics(
                symbol_cache,
                global_metadata.get('total_symbols_in_patterns_frequencies', 0),
                global_metadata.get('total_pattern_frequencies', 0),
                global_metadata.get('total_unique_patterns', 0),
            )
            # The STM as the candidates were matched against it. A caller that
            # passes no event structure gets the state read as one event.
            observation = Observation(stm_events if stm_events and any(stm_events) else [state], node)

            # Sets bayesian_prior, bayesian_likelihood, good_odds, potential,
            # bayesian_posterior and predictive_information on every candidate.
            scores = score_ensemble(causal_patterns, observation, node)
            if scores.candidate_frequency > node.total_pattern_frequency:
                # total_pattern_frequencies counts every learn, so it can never
                # be smaller than the frequencies of some of the node's
                # patterns. A node whose counter was written before it counted
                # re-learns is the one way it is; the priors are then taken
                # against the candidates' own total, which keeps them at or
                # below 1, until the counter is recounted.
                logger.warning(
                    "%s total_pattern_frequencies is %d but the %d candidates of this request were learned "
                    "%d times. Recount it with scripts/recount_pattern_frequencies.py.",
                    self.kb_id, node.total_pattern_frequency, len(causal_patterns), scores.candidate_frequency,
                )

            def ranked(predictions):
                # rank_predictions tie-breaks on the pattern name, which is what
                # makes repeated identical requests return the same predictions
                # in the same order -- see its docstring.
                try:
                    return rank_predictions(predictions, settings.rank_sort_algo, settings.max_predictions)
                except KeyError:
                    raise ValueError(f"Invalid rank_sort_algo '{settings.rank_sort_algo}': metric not found in predictions. Available metrics: {list(predictions[0].keys()) if predictions else 'none'}")
                except Exception as e:
                    raise Exception(f"\nException in PatternProcessor.predictPattern (async): Error in sorting predictions! {self.kb_id}: {e}")

            # Rank and cut as soon as the ranking key exists. The metrics below
            # describe one prediction at a time, so they are worked out only
            # for the predictions that are returned -- unless the session ranks
            # by one of them, in which case every candidate needs it first.
            rank_after_pattern_metrics = settings.rank_sort_algo in PATTERN_METRICS
            if not rank_after_pattern_metrics:
                causal_patterns = ranked(causal_patterns)

            # Emotives, and the precomputed entropy/tf metrics from the same
            # patterns_metadata rows.
            precomputed_metrics = searcher.attach_pattern_metadata(causal_patterns)
            precomputed_hit = len(precomputed_metrics)
            if precomputed_hit > 0:
                logger.debug(f"Pre-computed metrics: {precomputed_hit} hits, {len(causal_patterns) - precomputed_hit} misses")

            for prediction in causal_patterns:
                # The pattern's own events. They are what past, present and
                # future were cut from, so the three rebuild them if needed.
                pattern_events = prediction.get('pattern_data') or (
                    prediction['past'] + prediction['present'] + prediction['future'])
                pattern_symbols = [s for event in pattern_events for s in event]
                pattern_length = len(pattern_symbols)

                # Average emotives (convert from list of dicts to single dict)
                try:
                    if isinstance(prediction['emotives'], list):
                        prediction['emotives'] = average_emotives(prediction['emotives'])
                except ZeroDivisionError as e:
                    logger.error(f"ZeroDivisionError in average_emotives: emotives={prediction['emotives']}, error={e}")
                    raise

                # Pattern-intrinsic entropy metrics: use pre-computed if available
                precomp = precomputed_metrics.get(prediction.get('name', ''))
                symbol_counts = Counter(pattern_symbols)

                if precomp:
                    entropy_val = precomp['entropy']
                    normalized_entropy_val = precomp['normalized_entropy']
                    global_normalized_entropy_val = precomp['global_normalized_entropy']
                elif pattern_symbols:
                    # Fallback: compute at runtime (pattern predates finalize-training).
                    # These are pattern-intrinsic, so they are computed over the
                    # whole pattern exactly as finalize_training does -- not over
                    # `present`, which is only the matched events and gave the same
                    # pattern a different value before and after finalization.
                    # Shannon entropy (log base 2)
                    entropy_val = 0.0
                    for count in symbol_counts.values():
                        if count > 0:
                            p = count / pattern_length
                            entropy_val -= p * log2(p)
                    normalized_entropy_val = normalized_entropy(pattern_symbols, total_symbols)
                    # The whole symbol table, as finalize_training uses: every
                    # symbol of the pattern has its own share of the node's
                    # patterns, whether or not it was observed.
                    pattern_probabilities = {
                        symbol: node.pattern_share(symbol) for symbol in symbol_counts
                    }
                    global_normalized_entropy_val = global_normalized_entropy(
                        pattern_symbols, pattern_probabilities, total_symbols
                    )
                else:
                    entropy_val = 0.0
                    normalized_entropy_val = 0.0
                    global_normalized_entropy_val = 0.0

                # TF-IDF: the pre-computed TF vector if there is one, else the
                # same shares counted from the pattern.
                tf_vector = precomp.get('tf_vector') if precomp else None
                if not tf_vector:
                    tf_vector = {symbol: count / pattern_length for symbol, count in symbol_counts.items()}

                prediction.update({
                    'entropy': entropy_val,
                    'normalized_entropy': normalized_entropy_val,
                    'global_normalized_entropy': global_normalized_entropy_val,
                    'itfdf_similarity': itfdf_similarity(
                        observation, prediction['present'], prediction['frequency'],
                        scores.candidate_frequency, node),
                    'confluence': confluence(
                        pattern_events, prediction['frequency'], scores.total_pattern_frequency, node),
                    'tfidf_score': tfidf_score(tf_vector, node),
                })

                # Remove pattern_data to save bandwidth
                prediction.pop('pattern_data', None)

            if rank_after_pattern_metrics:
                causal_patterns = ranked(causal_patterns)

            logger.debug(f" [ PatternProcessor predictPattern (async) ] {len(causal_patterns)} predictions returned")
            return PredictionResult(causal_patterns, scores.future_potentials, scores.chance_posterior)

        except Exception as e:
            raise Exception(f"\nException in PatternProcessor.predictPattern (async): Error in metrics calculation! {self.kb_id}: {e}")

    async def get_predictions_async(self, stm: list[list[str]], config=None) -> PredictionResult:
        """
        Generate predictions with session-specific configuration (async version).

        Config-as-parameter: the session's settings are passed down the predict
        path, and nothing on the processor is changed.

        Args:
            stm: Short-term memory (list of events)
            config: Optional SessionConfiguration with prediction parameters

        Returns:
            PredictionResult with the predictions, their future potentials and
            the chance posterior. When the STM holds no symbols nothing is
            predicted: both lists are empty and the chance posterior is None.
        """
        # Flatten STM to state
        state = list(chain(*stm))

        # Generate predictions if we have at least 1 string in state
        # Single-symbol predictions use optimized fast path
        if len(state) < 1:
            logger.debug("No symbols in state for predictions")
            return PredictionResult([], [])

        return await self._predict_with_config(state, stm, config)

    async def _predict_with_config(
        self,
        state: list[str],
        stm_events: list[list[str]],
        config: Optional[SessionConfiguration],
    ) -> PredictionResult:
        """predictPattern with the session's settings, releasing what it loaded."""
        settings = self._prediction_settings(config)
        try:
            return await self.predictPattern(state, stm_events=stm_events, settings=settings)
        finally:
            if settings.searcher is not self.patterns_searcher:
                settings.searcher.release_request_data()

    def _prediction_settings(self, config: Optional[SessionConfiguration]) -> PredictionSettings:
        """Resolve a request's prediction settings from its session configuration.

        Settings live in the session's stored configuration; this reads them.
        Each value comes from the session when it sets one and from the node
        default otherwise.

        The searcher carries the session's recall threshold, filter pipeline,
        fuzzy matching and affinity settings, so a session needs its own. It is
        built once and cached under the session id, then reused until the
        session's configuration changes. It is never shared between sessions:
        it holds per-request working state (affinity weights, the loaded
        candidates), and a session's requests are serialized by its session lock
        while other sessions' are not. The cache is bounded, least recently used
        first out. Without a configuration the processor's own searcher is used;
        a configuration with no session id gets a newly built, uncached one.
        """
        def pick(name, default):
            value = getattr(config, name, None) if config is not None else None
            return default if value is None else value

        max_predictions = pick('max_predictions', self.max_predictions)
        use_token_matching = pick('use_token_matching', self.use_token_matching)
        rank_sort_algo = pick('rank_sort_algo', self.rank_sort_algo)

        if config is None:
            return PredictionSettings(
                self.patterns_searcher, max_predictions, rank_sort_algo, use_token_matching)

        session_id = getattr(config, 'session_id', '') or ''
        fingerprint = repr(sorted(config.get_config_only().items()))
        cached = self._session_searchers.get(session_id) if session_id else None
        if cached is not None and cached[0] == fingerprint:
            searcher = cached[1]
            self._session_searchers.move_to_end(session_id)
        else:
            searcher = PatternSearcher(
                kb_id=self.kb_id,
                max_predictions=max_predictions,
                recall_threshold=pick('recall_threshold', self.recall_threshold),
                use_token_matching=use_token_matching,
                session_config=config,
                clickhouse_client=self.patterns_searcher.clickhouse_client,
                redis_client=self.patterns_searcher.redis_client,
            )
            if session_id:
                self._session_searchers[session_id] = (fingerprint, searcher)
                self._session_searchers.move_to_end(session_id)
                while len(self._session_searchers) > SESSION_SEARCHER_CACHE_SIZE:
                    self._session_searchers.popitem(last=False)
        return PredictionSettings(searcher, max_predictions, rank_sort_algo, use_token_matching)

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

        async def predictions_only():
            return (await self.get_predictions_async(stm, config)).predictions

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If we're in an async context, create a task
                return asyncio.create_task(predictions_only())
            else:
                return loop.run_until_complete(predictions_only())
        except RuntimeError:
            # No event loop, create one
            return asyncio.run(predictions_only())
