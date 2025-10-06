import asyncio
import heapq
import itertools
import logging
from collections import Counter, deque
from itertools import chain
from operator import itemgetter
from os import environ
from typing import Any, Optional

import numpy as np
import pymongo
from pymongo import ReturnDocument

from kato.informatics.knowledge_base import SuperKnowledgeBase
from kato.informatics.metrics import (
    average_emotives,
    confluence,
    grand_hamiltonian,
    hamiltonian,
)
from kato.informatics.predictive_information import calculate_ensemble_predictive_information
from kato.representations.pattern import Pattern
from kato.searches.pattern_search import PatternSearcher
from kato.storage.aggregation_pipelines import OptimizedQueryManager
from kato.storage.metrics_cache import CachedMetricsCalculator, get_metrics_cache_manager
from kato.utils.logging import get_logger

# Use enhanced logger with trace ID support
kato_logger = get_logger('kato.pattern_processor')
logger = logging.getLogger('kato.pattern_processor')  # Keep for compatibility
logger.setLevel(getattr(logging, environ.get('LOG_LEVEL', 'INFO')))
logger.info('logging initiated')

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
        self.superkb = SuperKnowledgeBase(self.kb_id, self.persistence, settings=self.settings)
        self.patterns_searcher = PatternSearcher(kb_id=self.kb_id,
                                             max_predictions=self.max_predictions,
                                             recall_threshold=self.recall_threshold)

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

        Empties the STM deque, disables prediction triggering, and clears emotives.
        """
        self.STM: deque[list[str]] = deque()
        self.trigger_predictions: bool = False
        self.emotives: list[dict[str, float]] = []
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

        Sets up empty STM, emotives, mood, and loads patterns from database.
        Called during initialization and memory clearing.
        """
        self.STM: deque[list[str]] = deque()
        self.emotives: list[dict[str, float]] = []
        self.mood: dict[str, float] = {}
        self.last_learned_pattern_name: Optional[str] = None
        self.patterns_searcher.getPatterns()
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
            # Store pattern with averaged emotives from all events
            x = self.patterns_kb.learnPattern(pattern, emotives=average_emotives(self.emotives))

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
            return self.last_learned_pattern_name
        self.emotives = []
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
        logger.debug(f"setCurrentEvent called with symbols: {symbols}")
        if symbols:
            self.STM.append(symbols)
            logger.debug(f"STM after append: {list(self.STM)}")
        else:
            logger.debug(f"No symbols to add, STM unchanged: {list(self.STM)}")
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
        try:
            # Use batch query for better performance
            symbol_stats = self.query_manager.get_symbol_frequencies_batch([symbol])
            return symbol_stats.get(symbol, 0)
        except Exception as e:
            logger.warning(f"Batch symbol query failed, falling back to find_one(): {e}")
            # Fallback to original method
            doc = self.superkb.symbols_kb.find_one({"name": symbol})
            return doc['frequency'] if doc else 0

    def symbolProbability(self, symbol: str, total_symbols_in_patterns_frequencies: int) -> float:
        """Calculate the probability of a symbol appearing in patterns.

        Args:
            symbol: Symbol name to calculate probability for.
            total_symbols_in_patterns_frequencies: Total frequency count across all symbols.

        Returns:
            Probability value between 0.0 and 1.0.
        """
        # We can either look at using the probability of a symbol to appear anywhere in the KB, which means it can also appear
        # multiple times in one pattern, or we can look at the probability of a symbol to appear in any pattern, regardless
        # of the number of times it appears within any one pattern.
        # We can also look at coming up with a formula to account for both to affect the potential.
        try:
            # Use batch query for better performance
            symbol_stats = self.query_manager.get_symbol_frequencies_batch([symbol])
            symbol_data = symbol_stats.get(symbol, {})
            pattern_member_frequency = symbol_data.get('pattern_member_frequency', 0)
            return float(pattern_member_frequency / total_symbols_in_patterns_frequencies) if total_symbols_in_patterns_frequencies > 0 else 0.0
        except Exception as e:
            logger.warning(f"Batch symbol query failed in symbolProbability, falling back to find_one(): {e}")
            # Fallback to original method
            doc = self.superkb.symbols_kb.find_one({"name": symbol})
            if doc and total_symbols_in_patterns_frequencies > 0:
                return float(doc['pattern_member_frequency'] / total_symbols_in_patterns_frequencies)
            return 0.0

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
            symbol_frequency_cache = Counter()
            total_ensemble_pattern_frequencies = 0

            # Use optimized aggregation pipeline to load all symbols
            try:
                symbol_cache = self.query_manager.get_all_symbols_optimized(
                    self.superkb.symbols_kb
                )
                logger.debug(f"Loaded {len(symbol_cache)} symbols using optimized aggregation pipeline (async)")
            except Exception as e:
                logger.warning(f"Aggregation pipeline failed for symbols in async, falling back to find(): {e}")
                # Fallback to original method
                symbol_cache = {}
                all_symbols = self.superkb.symbols_kb.find({}, {'_id': False}, cursor_type=pymongo.CursorType.EXHAUST)
                for symbol in all_symbols:
                    symbol_cache[symbol['name']] = symbol

            # Calculate totals and caches
            for prediction in causal_patterns:
                total_ensemble_pattern_frequencies += prediction['frequency']
                # Flatten missing if it's event-structured (list of lists)
                missing_symbols_calc = prediction['missing']
                if missing_symbols_calc and isinstance(missing_symbols_calc[0], list):
                    missing_symbols_calc = [s for event in missing_symbols_calc for s in event]
                for symbol in itertools.chain(prediction['matches'], missing_symbols_calc):
                    if symbol not in symbol_probability_cache or symbol not in symbol_frequency_cache:
                        if symbol not in symbol_cache:
                            symbol_probability_cache[symbol] = 0
                            symbol_frequency_cache[symbol] = 0
                            continue
                        symbol_data = symbol_cache[symbol]
                        if total_symbols_in_patterns_frequencies > 0:
                            symbol_probability = float(symbol_data['pattern_member_frequency'] / total_symbols_in_patterns_frequencies)
                        else:
                            symbol_probability = 0.0
                        symbol_probability_cache[symbol] = symbol_probability
                        symbol_frequency_cache[symbol] += symbol_data['frequency']

            symbol_frequency_in_state = Counter(state)
            for symbol in symbol_frequency_in_state:
                if symbol not in symbol_frequency_cache:
                    symbol_frequency_cache[symbol] = 0

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
                        hamiltonian_val = await self.cached_calculator.hamiltonian_cached(
                            state, total_symbols, symbol_probability_cache
                        )
                        grand_hamiltonian_val = await self.cached_calculator.grand_hamiltonian_cached(
                            state, symbol_probability_cache
                        )
                    except Exception as e:
                        logger.warning(f"Cached metrics calculation failed: {e}, falling back to direct calculation")
                        hamiltonian_val = hamiltonian(state, total_symbols)
                        grand_hamiltonian_val = grand_hamiltonian(state, symbol_probability_cache, total_symbols)
                else:
                    # Fallback to direct calculation
                    hamiltonian_val = hamiltonian(state, total_symbols)
                    grand_hamiltonian_val = grand_hamiltonian(state, symbol_probability_cache, total_symbols)

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
                                [_present], symbol_probability_cache
                            )
                            confluence_val = _p_e_h * (1 - conditional_prob)
                        except Exception as e:
                            logger.debug(f"Cached conditional probability failed: {e}, falling back to direct calculation")
                            confluence_val = confluence(_p_e_h, _present, symbol_probability_cache)
                    else:
                        confluence_val = confluence(_p_e_h, _present, symbol_probability_cache)
                except Exception as e:
                    logger.debug(f"Error calculating confluence: {e}")
                    confluence_val = 0.0

                # Average emotives (convert from list of dicts to single dict)
                try:
                    prediction['emotives'] = average_emotives(prediction['emotives'])
                except ZeroDivisionError as e:
                    logger.error(f"ZeroDivisionError in average_emotives: emotives={prediction['emotives']}, error={e}")
                    raise

                # Update prediction with calculated values
                prediction.update({
                    'hamiltonian': hamiltonian_val,
                    'grand_hamiltonian': grand_hamiltonian_val,
                    'itfdf_similarity': itfdf_similarity,
                    'confluence': confluence_val
                })

                # Remove pattern_data to save bandwidth
                prediction.pop('pattern_data', None)

            # Calculate ensemble-based predictive information and update potentials
            try:
                causal_patterns, future_potentials = calculate_ensemble_predictive_information(causal_patterns)
                # Store future_potentials for the API response
                self.future_potentials = future_potentials
            except Exception as e:
                logger.error(f"Error in ensemble predictive information calculation: {e}")
                # Set defaults if calculation fails - use old formula as fallback
                for prediction in causal_patterns:
                    if 'predictive_information' not in prediction:
                        prediction['predictive_information'] = 0.0
                    if 'potential' not in prediction:
                        # Use old formula as fallback
                        try:
                            prediction['potential'] = (prediction['evidence'] + prediction['confidence']) * prediction['snr'] + prediction.get('itfdf_similarity', 0.0) + (1/(prediction['fragmentation'] + 1))
                        except ZeroDivisionError:
                            prediction['potential'] = (prediction['evidence'] + prediction['confidence']) * prediction['snr'] + prediction.get('itfdf_similarity', 0.0)
                self.future_potentials = []

            try:
                active_causal_patterns = sorted(list(heapq.nlargest(self.max_predictions, causal_patterns, key=itemgetter('potential'))), reverse=True, key=itemgetter('potential'))
            except Exception as e:
                raise Exception(f"\nException in PatternProcessor.predictPattern (async): Error in sorting predictions! {self.kb_id}: {e}")

            logger.debug(f" [ PatternProcessor predictPattern (async) ] {len(active_causal_patterns)} active_causal_patterns")
            return active_causal_patterns

        except Exception as e:
            raise Exception(f"\nException in PatternProcessor.predictPattern (async): Error in metrics calculation! {self.kb_id}: {e}")
