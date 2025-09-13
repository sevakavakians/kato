"""
Memory Manager for KATO
Handles Short-Term Memory (STM) and Long-Term Memory (LTM) operations.
Extracted from KatoProcessor for better modularity.
"""

import logging
from typing import List, Dict, Any, Optional
from collections import deque

from kato.informatics.metrics import average_emotives
from kato.exceptions import MemoryOperationError

logger = logging.getLogger('kato.workers.memory_manager')


class MemoryManager:
    """
    Manages memory operations for KATO processor.
    
    This class handles:
    - STM (Short-Term Memory) state management
    - Variable resets and initialization
    - Memory clearing operations
    - Emotives accumulation and averaging
    """
    
    def __init__(self, pattern_processor, vector_processor):
        """
        Initialize memory manager with references to processors.
        
        Args:
            pattern_processor: Reference to pattern processor for STM operations
            vector_processor: Reference to vector processor for vector memory operations
        """
        self.pattern_processor = pattern_processor
        self.vector_processor = vector_processor
        
        # Initialize state variables
        self.symbols: List[str] = []
        self.current_emotives: Dict[str, float] = {}
        self.emotives_accumulator: List[Dict[str, float]] = []  # v2.0: For session isolation
        self.last_command: str = ""
        self.percept_data: Dict[str, Any] = {}
        self.percept_data_vector: Optional[List[float]] = None
        self.time: int = 0
        
        logger.debug("MemoryManager initialized")
    
    def reset_primitive_variables(self) -> None:
        """
        Reset primitive variables to their initial state.
        
        This is called when clearing STM or starting fresh observations.
        Does not affect the time counter or pattern memory.
        """
        try:
            self.symbols = []
            self.current_emotives = {}
            self.emotives_accumulator = []  # v2.0: Reset emotives accumulator
            self.last_command = ""
            self.pattern_processor.v_identified = []
            self.percept_data = {}
            self.percept_data_vector = None
            logger.debug("Primitive variables reset")
        except Exception as e:
            raise MemoryOperationError(
                f"Failed to reset primitive variables: {str(e)}",
                memory_type="STM",
                operation="reset_variables"
            )
    
    def clear_stm(self) -> None:
        """
        Clear Short-Term Memory.
        
        Resets STM in pattern processor and clears associated state variables.
        This does not affect learned patterns in long-term memory.
        """
        try:
            # Reset primitive variables
            self.reset_primitive_variables()
            
            # Clear symbols list
            self.symbols = []
            
            # Clear STM in pattern processor
            self.pattern_processor.clear_stm()
            
            logger.info("STM cleared successfully")
        except Exception as e:
            raise MemoryOperationError(
                f"Failed to clear STM: {str(e)}",
                memory_type="STM",
                operation="clear"
            )
    
    def clear_all_memory(self) -> None:
        """
        Clear all memory (both STM and LTM).
        
        This is a complete memory wipe including:
        - Short-term memory (STM)
        - Long-term memory (patterns in database)
        - Vector memory
        - All state variables
        - Time counter reset
        
        WARNING: This operation cannot be undone and will delete all learned patterns.
        """
        try:
            # Reset time counter
            self.time = 0
            
            # Clear command history
            self.last_command = ""
            
            # Clear emotives
            self.current_emotives = {}
            
            # Clear STM
            self.clear_stm()
            
            # Clear pattern processor memory (includes database operations)
            self.pattern_processor.superkb.clear_all_memory()
            self.pattern_processor.clear_all_memory()
            
            # Clear vector processor memory
            self.vector_processor.clear_all_memory()
            
            logger.info("All memory cleared successfully (STM and LTM)")
        except Exception as e:
            raise MemoryOperationError(
                f"Failed to clear all memory: {str(e)}",
                memory_type="ALL",
                operation="clear"
            )
    
    def increment_time(self) -> None:
        """
        Increment the internal time counter.
        
        This counter tracks the number of observations processed.
        """
        self.time += 1
        logger.debug(f"Time incremented to {self.time}")
    
    def process_emotives(self, emotives: Dict[str, float]) -> None:
        """
        Process and accumulate emotives data.
        
        Args:
            emotives: Dictionary of emotive values to process
            
        Updates:
            - Adds emotives to pattern processor's accumulator
            - Calculates and stores averaged emotives in current_emotives
        """
        try:
            if emotives:
                # Add to pattern processor's emotives list
                self.pattern_processor.emotives += [emotives]
                
                # Calculate average of all accumulated emotives
                self.current_emotives = average_emotives(self.pattern_processor.emotives)
                
                logger.debug(f"Processed emotives: {len(emotives)} values, "
                           f"current average: {len(self.current_emotives)} dimensions")
        except Exception as e:
            raise MemoryOperationError(
                f"Failed to process emotives: {str(e)}",
                memory_type="STM",
                operation="process_emotives",
                context={"emotives_count": len(emotives) if emotives else 0}
            )
    
    def update_percept_data(self, strings: List[str], vectors: List[List[float]], 
                           emotives: Dict[str, float], path: List[str], 
                           metadata: Dict[str, Any]) -> None:
        """
        Update the current percept data.
        
        Args:
            strings: String observations
            vectors: Vector observations
            emotives: Emotional values
            path: Processing path
            metadata: Additional metadata
        """
        self.percept_data = {
            'strings': strings,
            'vectors': vectors,
            'emotives': emotives,
            'path': path,
            'metadata': metadata
        }
        logger.debug(f"Percept data updated with {len(strings)} strings, "
                    f"{len(vectors)} vectors")
    
    def get_stm_state(self) -> List[List[str]]:
        """
        Get the current STM state.
        
        Returns:
            Current STM as list of symbol lists
        """
        return list(self.pattern_processor.STM)
    
    def get_stm_length(self) -> int:
        """
        Get the current length of STM.
        
        Returns:
            Number of events in STM
        """
        return len(self.pattern_processor.STM)
    
    def set_stm_tail_context(self, tail_event: List[str]) -> None:
        """
        Set STM with a tail event for context continuity.
        
        Used during auto-learning to maintain context between learned patterns.
        
        Args:
            tail_event: The last event to keep as context
        """
        try:
            self.pattern_processor.setSTM([tail_event])
            logger.debug(f"STM tail context set with {len(tail_event)} symbols")
        except Exception as e:
            raise MemoryOperationError(
                f"Failed to set STM tail context: {str(e)}",
                memory_type="STM",
                operation="set_tail_context"
            )