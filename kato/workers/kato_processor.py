# cimport cython
import asyncio
import logging
import os
from multiprocessing import Lock, cpu_count

from kato.config.session_config import SessionConfiguration
from kato.config.settings import get_settings
from kato.workers.memory_manager import MemoryManager
from kato.workers.observation_processor import ObservationProcessor
from kato.workers.pattern_operations import PatternOperations
from kato.workers.pattern_processor import PatternProcessor
from kato.workers.vector_processor import VectorProcessor

logger = logging.getLogger('kato.workers.kato-processor')
# Logger level will be set when first instance is created


class KatoProcessor:
    def __init__(self, name: str, processor_id: str, settings=None, **genome_manifest):
        '''Initialize KATO processor as a stateless execution engine.

        Configuration is now session-based only - no processor-level config state.
        All runtime config must be passed as parameters to observe() and get_predictions().
        '''
        # Accept settings via dependency injection, fallback to get_settings() for compatibility
        if settings is None:
            settings = get_settings()
        self.settings = settings

        # Configure logger level if not already set
        if logger.level == 0:  # Logger level not set
            logger.setLevel(getattr(logging, settings.logging.log_level))

        self.id = processor_id
        self.name = name

        # Get service name from environment
        self.agent_name = os.environ.get('SERVICE_NAME', 'kato')
        logger.info(f" Starting KatoProcessor ID: {self.id}, Name: {self.name}")

        # Use all available processors for parallel searches
        self.procs_for_searches = int(cpu_count())

        # Create minimal manifest with only essential processor info
        minimal_manifest = {
            'name': self.name,
            'kb_id': self.id,
            # Use settings defaults for processor initialization
            'indexer_type': settings.processing.indexer_type,
            'sort': settings.processing.sort_symbols,
            'process_predictions': settings.processing.process_predictions,
            'max_pattern_length': settings.learning.max_pattern_length,
            'recall_threshold': settings.learning.recall_threshold,
            'max_predictions': settings.processing.max_predictions,
            'use_token_matching': settings.processing.use_token_matching,
            'stm_mode': settings.learning.stm_mode,
            'persistence': settings.learning.persistence,
            'rank_sort_algo': settings.processing.rank_sort_algo
        }

        self.vector_processor = VectorProcessor(self.procs_for_searches, **minimal_manifest)
        self.pattern_processor = PatternProcessor(settings=self.settings, **minimal_manifest)
        # Access collections directly from superkb (hybrid architecture)
        self.pattern_processor.patterns_kb = self.pattern_processor.superkb.patterns_kb
        self.predictions_kb = self.pattern_processor.superkb.predictions_kb

        # Mark components that need async initialization
        self._metrics_cache_initialized = False
        self.distributed_stm_manager = None
        self._async_initialization_pending = True

        self.processing_lock = Lock()

        # Initialize extracted modules
        self.memory_manager = MemoryManager(self.pattern_processor, self.vector_processor)
        self.pattern_operations = PatternOperations(
            self.pattern_processor, self.vector_processor,
            self.memory_manager
        )
        self.observation_processor = ObservationProcessor(
            self.vector_processor, self.pattern_processor,
            self.memory_manager, self.pattern_operations,
            self.pattern_processor.sort, self.pattern_processor.max_pattern_length,
            settings.processing.process_predictions
        )

        logger.info(f" {self.name}-{self.id} kato processor, ready!")
        return

    async def initialize_async_components(self):
        """
        Initialize async components after processor creation.
        Should be called once after processor instantiation.
        """
        if not self._async_initialization_pending:
            return  # Already initialized

        try:
            # Initialize metrics cache for pattern processor
            if not self._metrics_cache_initialized:
                await self.pattern_processor.initialize_metrics_cache()
                self._metrics_cache_initialized = True
                logger.info(f"Metrics cache initialized for processor {self.id}")
        except Exception as e:
            logger.warning(f"Failed to initialize metrics cache for processor {self.id}: {e}")

        try:
            # Initialize distributed STM if Redis is available
            from kato.storage.redis_streams import get_distributed_stm_manager
            self.distributed_stm_manager = await get_distributed_stm_manager(self.id)
            if self.distributed_stm_manager:
                logger.info(f"Distributed STM initialized for processor {self.id}")
            else:
                logger.info("Distributed STM not available - using local STM only")
        except Exception as e:
            logger.warning(f"Failed to initialize distributed STM for processor {self.id}: {e}")
            self.distributed_stm_manager = None

        self._async_initialization_pending = False
        logger.info(f"Async initialization completed for processor {self.id}")

    def __primitive_variables_reset__(self):
        """Reset primitive variables - delegates to memory manager"""
        self.memory_manager.reset_primitive_variables()
        # Update local references
        self.symbols = self.memory_manager.symbols
        self.current_emotives = self.memory_manager.current_emotives
        self.percept_data = self.memory_manager.percept_data
        return

    def _process_vectors_(self, vector_data):
        """Process vectors - delegates to observation processor"""
        return self.observation_processor.process_vectors(vector_data)

    def _process_emotives_(self, emotives):
        """Process emotives - delegates to observation processor"""
        self.observation_processor.process_emotives(emotives)
        self.current_emotives = self.memory_manager.current_emotives
        return

    def get_pattern(self, pattern_id):
        """Retrieve pattern information by pattern ID - delegates to pattern operations"""
        return self.pattern_operations.get_pattern(pattern_id)

    def get_vector(self, name):
        """Retrieve vector values - delegates to pattern operations"""
        return self.pattern_operations.get_vector(name)

    async def clear_stm(self):
        """Clear STM - delegates to memory manager"""
        self.memory_manager.clear_stm()
        self.predictions = []
        # Update local references
        self.symbols = self.memory_manager.symbols

        # Publish clear event to distributed STM if available
        if self.distributed_stm_manager:
            try:
                await self.distributed_stm_manager.clear_stm_distributed()
            except Exception as e:
                logger.warning(f"Failed to publish clear STM to distributed STM: {e}")
        self.current_emotives = self.memory_manager.current_emotives
        self.percept_data = self.memory_manager.percept_data
        return

    def clear_all_memory(self):
        """Clear all memory - delegates to memory manager"""
        self.memory_manager.clear_all_memory()
        self.predictions = []
        # Update local references
        self.time = self.memory_manager.time
        self.symbols = self.memory_manager.symbols
        self.current_emotives = self.memory_manager.current_emotives
        self.percept_data = self.memory_manager.percept_data
        return

    def learn(
        self,
        *,
        session_state: 'SessionState',
        keep_tail: bool = False
    ) -> tuple[str, list[list[str]]]:
        """
        Learn a pattern from session STM and return updated STM.

        STATELESS: Takes session state, returns pattern name and new STM.
        Does NOT mutate processor or session_state.

        Args:
            session_state: Current session state with STM to learn
            keep_tail: Whether to keep last event in STM after learning (for rolling mode)

        Returns:
            Tuple of (pattern_name, new_stm):
            - pattern_name: Name of learned pattern (or None if learning failed)
            - new_stm: Updated STM after learning
        """
        # BRIDGE: Load session STM into pattern processor temporarily
        self.memory_manager.set_stm_in_pattern_processor(
            self.pattern_processor,
            session_state.stm
        )

        # TODO (Phase 1.7): Update pattern_operations to be stateless
        # For now, it reads from pattern_processor.STM and mutates it
        pattern_name = self.pattern_operations.learn_pattern(keep_tail=keep_tail)

        # Extract new STM after learning
        new_stm = MemoryManager.get_stm_from_pattern_processor(self.pattern_processor)

        return pattern_name, new_stm

    def delete_pattern(self, name):
        """Delete pattern - delegates to pattern operations"""
        return self.pattern_operations.delete_pattern(name)

    def update_pattern(self, name, frequency, emotives):
        """Update pattern - delegates to pattern operations"""
        return self.pattern_operations.update_pattern(name, frequency, emotives)

    async def observe(
        self,
        observation: dict,
        *,
        session_state: 'SessionState',
        config: SessionConfiguration
    ) -> dict:
        """
        Process incoming observations and return updated session state.

        STATELESS: Takes session state as input, returns new state as output.
        Does NOT mutate processor instance or session_state input.

        This is the main entry point for new sensory data. It handles:
        - String symbols (already in symbolic form)
        - Vectors (converted to symbols via vector processor)
        - Emotives (emotional/utility values)
        - Auto-learning when max_pattern_length is reached

        Args:
            observation: Observation data (strings, vectors, emotives, metadata)
            session_state: Current session state (SessionState from Redis)
            config: SessionConfiguration for session-specific behavior (REQUIRED)

        Returns:
            Dictionary with updated state:
            {
                'status': 'observed',
                'stm': list[list[str]],              # New STM
                'time': int,                         # New time
                'emotives_accumulator': list[dict],  # New emotives
                'metadata_accumulator': list[dict],  # New metadata
                'percept_data': dict,                # New percept
                'predictions': list,                 # New predictions
                'auto_learned_pattern': str | None,  # If auto-learn triggered
                'unique_id': str,
                'symbols': list[str],                # Combined symbols
                'instance_id': str
            }
        """
        # BRIDGE: Load session STM into pattern processor temporarily
        # (Until observation_processor is made stateless in Phase 1.6)
        self.memory_manager.set_stm_in_pattern_processor(
            self.pattern_processor,
            session_state.stm
        )

        # TODO (Phase 1.6): Update observation_processor to accept session_state
        # For now, it will mutate memory_manager state (legacy behavior)
        result = await self.observation_processor.process_observation(observation, config=config)

        # BRIDGE: Extract new state from pattern processor and helpers
        new_stm = MemoryManager.get_stm_from_pattern_processor(self.pattern_processor)
        new_time = MemoryManager.increment_time(session_state.time)

        # Process emotives using stateless helper
        new_emotives_acc, new_current_emotives = MemoryManager.process_emotives(
            session_state.emotives_accumulator,
            observation.get('emotives', {})
        )

        # Process metadata using stateless helper
        new_metadata_acc = MemoryManager.process_metadata(
            session_state.metadata_accumulator,
            observation.get('metadata', {})
        )

        # Build percept data using stateless helper
        new_percept = MemoryManager.build_percept_data(
            strings=observation.get('strings', []),
            vectors=observation.get('vectors', []),
            emotives=new_current_emotives,
            path=result.get('path', []),
            metadata=observation.get('metadata', {})
        )

        # Publish to distributed STM if available
        if self.distributed_stm_manager and observation:
            try:
                await self.distributed_stm_manager.observe_distributed(observation)
            except Exception as e:
                logger.warning(f"Failed to publish observation to distributed STM: {e}")

        # Return new state (no mutation of inputs)
        return {
            'status': 'observed',
            'stm': new_stm,
            'time': new_time,
            'emotives_accumulator': new_emotives_acc,
            'metadata_accumulator': new_metadata_acc,
            'percept_data': new_percept,
            'predictions': result.get('predictions', []),
            'auto_learned_pattern': result.get('auto_learned_pattern'),
            'unique_id': result.get('unique_id', observation.get('unique_id', '')),
            'symbols': result.get('symbols', []),
            'instance_id': self.id
        }

    async def get_predictions(
        self,
        *,
        session_state: 'SessionState',
        config: SessionConfiguration,
        unique_id: str = None
    ) -> list:
        """
        Get predictions based on session STM.

        STATELESS: Takes session state, returns predictions.
        Does NOT mutate processor or session_state.

        If unique_id provided, retrieves stored predictions from database.
        Otherwise generates new predictions based on current STM.

        Args:
            session_state: Current session state
            config: Session configuration (recall threshold, max predictions, etc.)
            unique_id: Optional unique ID to retrieve stored predictions

        Returns:
            List of prediction objects
        """
        if unique_id:
            # Retrieve stored predictions from database (no state needed)
            return self.pattern_operations.get_predictions(unique_id)

        # Generate new predictions from current STM
        # BRIDGE: Load session STM into pattern processor temporarily
        self.memory_manager.set_stm_in_pattern_processor(
            self.pattern_processor,
            session_state.stm
        )

        # TODO (Phase 1.7): Update pattern_operations to accept session_state
        # For now, use get_predictions_with_config which reads from pattern_processor.STM
        return await self.pattern_operations.get_predictions_with_config(
            stm=session_state.stm,
            config=config
        )

    def get_stm(self):
        """Get the current short-term memory - delegates to memory manager"""
        logger.debug(f'get_stm called in {self.name}-{self.id}')
        stm_data = self.memory_manager.get_stm_state()
        logger.debug(f"get_stm returning: {stm_data}")
        return stm_data

    def get_percept_data(self):
        """Return percept data"""
        return self.memory_manager.percept_data

    @property
    def cognition_data(self):
        """Return cognition data"""
        return {
            'predictions': self.predictions,
            'emotives': self.memory_manager.current_emotives,
            'symbols': self.memory_manager.symbols,
            'command': self.memory_manager.last_command,
            'metadata': {},
            'path': [],
            'strings': [],
            'vectors': [],
            'short_term_memory': self.memory_manager.get_stm_state()
        }

    # ========================================================================
    # v3.0 Session State Management Methods
    # ========================================================================

    def set_stm(self, stm):
        """
        Set the short-term memory to a specific state.
        Used for session isolation in v2.0.

        Args:
            stm: List of event lists representing the STM state
        """
        # Set the STM in the pattern processor which maintains the proper structure
        from collections import deque
        # Fix: Convert list to deque to maintain type consistency
        self.pattern_processor.STM = deque(stm) if stm else deque()
        return

    def set_emotives_accumulator(self, emotives_acc):
        """
        Set the emotives accumulator to a specific state.
        Used for session isolation in v2.0.

        Args:
            emotives_acc: List of emotive dictionaries
        """
        self.memory_manager.emotives_accumulator = emotives_acc.copy() if emotives_acc else []
        return

    def get_emotives_accumulator(self):
        """
        Get the current emotives accumulator state.
        Used for session persistence in v2.0.

        Returns:
            List of emotive dictionaries
        """
        return self.memory_manager.emotives_accumulator.copy() if hasattr(self.memory_manager, 'emotives_accumulator') else []

    def set_metadata_accumulator(self, metadata_acc):
        """
        Set the metadata accumulator to a specific state.
        Used for session isolation in v2.0.

        Args:
            metadata_acc: List of metadata dictionaries
        """
        self.memory_manager.metadata_accumulator = metadata_acc.copy() if metadata_acc else []
        return

    def get_metadata_accumulator(self):
        """
        Get the current metadata accumulator state.
        Used for session persistence in v2.0.

        Returns:
            List of metadata dictionaries
        """
        return self.memory_manager.metadata_accumulator.copy() if hasattr(self.memory_manager, 'metadata_accumulator') else []
