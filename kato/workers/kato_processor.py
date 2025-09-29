# cimport cython
import logging
import os
import traceback
from typing import Counter
from multiprocessing import cpu_count, Lock

from kato.workers.vector_processor import VectorProcessor
from kato.workers.pattern_processor import PatternProcessor
from kato.workers.memory_manager import MemoryManager
from kato.workers.observation_processor import ObservationProcessor
from kato.workers.pattern_operations import PatternOperations
from kato.informatics.metrics import average_emotives
from kato.config.settings import get_settings




logger = logging.getLogger('kato.workers.kato-processor')
# Logger level will be set when first instance is created
logger.info('logging initiated')


class KatoProcessor:
    def __init__(self, genome_manifest, processor_id: str, settings=None, **kwargs):
        '''genome is the specific kato processor's genes.'''
        # Accept settings via dependency injection, fallback to get_settings() for compatibility
        if settings is None:
            settings = get_settings()
        self.settings = settings
        
        # Configure logger level if not already set
        if logger.level == 0:  # Logger level not set
            logger.setLevel(getattr(logging, settings.logging.log_level))
        
        self.genome_manifest = genome_manifest
        self.id = processor_id  # Direct processor ID parameter instead of from genome_manifest
        self.name = self.genome_manifest["name"]
        self.vector_indexer_type = self.genome_manifest["indexer_type"]
        # Get service name from environment
        self.agent_name = os.environ.get('SERVICE_NAME', 'kato')
        logger.info(" Starting KatoProcessor ID: %s" %self.id)

        self.SORT = self.genome_manifest["sort"]
        self.time = 0

        # Use all available processors for parallel searches
        self.procs_for_searches = int(cpu_count())

        self.genome_manifest["kb_id"] = self.id
        self.vector_processor = VectorProcessor(self.procs_for_searches, **self.genome_manifest)
        self.pattern_processor = PatternProcessor(settings=self.settings, **self.genome_manifest)
        self.knowledge = self.pattern_processor.superkb.knowledge
        self.pattern_processor.patterns_kb = self.pattern_processor.superkb.patterns_kb
        self.predictions_kb = self.knowledge.predictions_kb
        
        # Initialize metrics cache for pattern processor - schedule async init
        import asyncio
        try:
            # Try to run async initialization in the current event loop if available
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Schedule initialization to run later
                asyncio.create_task(self.pattern_processor.initialize_metrics_cache())
            else:
                # Run synchronously if no event loop is running
                loop.run_until_complete(self.pattern_processor.initialize_metrics_cache())
        except RuntimeError:
            # No event loop running, create one
            asyncio.run(self.pattern_processor.initialize_metrics_cache())

        # Initialize distributed STM if Redis is available
        self.distributed_stm_manager = None
        try:
            from kato.storage.redis_streams import get_distributed_stm_manager
            # Handle async initialization properly within existing event loop
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Schedule initialization to run later
                async def init_distributed_stm():
                    self.distributed_stm_manager = await get_distributed_stm_manager(self.id)
                    if self.distributed_stm_manager:
                        logger.info(f"Distributed STM initialized for processor {self.id}")
                    else:
                        logger.info("Distributed STM not available - using local STM only")
                asyncio.create_task(init_distributed_stm())
            else:
                # Run synchronously if no event loop is running
                self.distributed_stm_manager = loop.run_until_complete(get_distributed_stm_manager(self.id))
                if self.distributed_stm_manager:
                    logger.info(f"Distributed STM initialized for processor {self.id}")
                else:
                    logger.info("Distributed STM not available - using local STM only")
        except Exception as e:
            logger.warning(f"Failed to initialize distributed STM: {e}")
            self.distributed_stm_manager = None

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
            self.SORT, self.pattern_processor.max_pattern_length
        )
        
        # Initialize state through memory manager
        self.memory_manager.reset_primitive_variables()
        
        # Expose commonly accessed attributes for backward compatibility
        self.symbols = self.memory_manager.symbols
        self.current_emotives = self.memory_manager.current_emotives
        self.percept_data = self.memory_manager.percept_data
        self.time = self.memory_manager.time

        self.predictions = []
        logger.info(f" {self.name}-{self.id} kato processor, ready!")
        return

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

    def clear_stm(self):
        """Clear STM - delegates to memory manager"""
        self.memory_manager.clear_stm()
        self.predictions = []
        # Update local references
        self.symbols = self.memory_manager.symbols
        
        # Publish clear event to distributed STM if available
        if self.distributed_stm_manager:
            try:
                asyncio.run(self.distributed_stm_manager.clear_stm_distributed())
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

    def learn(self):
        """Learn pattern - delegates to pattern operations"""
        return self.pattern_operations.learn_pattern()

    def delete_pattern(self, name):
        """Delete pattern - delegates to pattern operations"""
        return self.pattern_operations.delete_pattern(name)

    def update_pattern(self, name, frequency, emotives):
        """Update pattern - delegates to pattern operations"""
        return self.pattern_operations.update_pattern(name, frequency, emotives)

    def observe(self, data=None):
        """
        Process incoming observations - delegates to observation processor.
        
        This is the main entry point for new sensory data. It handles:
        - String symbols (already in symbolic form)
        - Vectors (converted to symbols via vector processor)
        - Emotives (emotional/utility values)
        - Auto-learning when max_pattern_length is reached
        """
        # Process observation through the observation processor
        result = self.observation_processor.process_observation(data)
        
        # Update local state from result
        self.predictions = result.get('predictions', [])
        self.symbols = self.memory_manager.symbols
        self.current_emotives = self.memory_manager.current_emotives
        self.percept_data = self.memory_manager.percept_data
        self.time = self.memory_manager.time
        
        # Publish to distributed STM if available
        if self.distributed_stm_manager and data:
            try:
                asyncio.run(self.distributed_stm_manager.observe_distributed(data))
            except Exception as e:
                logger.warning(f"Failed to publish observation to distributed STM: {e}")
        
        # Return format expected by callers
        return {
            'status': 'observed',
            'unique_id': result['unique_id'],
            'auto_learned_pattern': result.get('auto_learned_pattern'),
            'symbols': result.get('symbols', []),  # Include combined symbols (strings + VCTR names)
            'time': self.time,
            'instance_id': self.id
        }
            
    def get_predictions(self, unique_id={}):
        """
        Retrieve predictions - delegates to pattern operations.
        
        If no ID provided, returns the most recent predictions from memory.
        Otherwise queries the database for stored predictions.
        """
        uid = None
        if unique_id:
            uid = unique_id.get('unique_id')
        
        if not uid:
            # Return cached predictions from last observe() call
            return self.predictions
        else:
            # Delegate to pattern operations for database query
            return self.pattern_operations.get_predictions(uid)

    def getGene(self, gene_name):
        """Return the value of a gene parameter"""
        logger.debug(f'getGene called with {gene_name} for {self.name}-{self.id}')
        return getattr(self.pattern_processor, gene_name, None)

    def get_stm(self):
        """Get the current short-term memory - delegates to memory manager"""
        logger.debug(f'get_stm called in {self.name}-{self.id}')
        stm_data = self.memory_manager.get_stm_state()
        logger.info(f"DEBUG get_stm returning: {stm_data}")
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

    def update_genes(self, genes):
        """Update gene values"""
        logger.debug(f'update_genes called with {genes} for {self.name}-{self.id}')
        for gene_name, value in genes.items():
            if hasattr(self.pattern_processor, gene_name):
                setattr(self.pattern_processor, gene_name, value)
                # Also update observation processor's copy for specific genes
                if gene_name == 'max_pattern_length':
                    self.observation_processor.max_pattern_length = value
                # No need to update stm_mode in observation_processor - it reads from pattern_processor
        return "genes-updated"
    
    # ========================================================================
    # v2.0 Session State Management Methods
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
